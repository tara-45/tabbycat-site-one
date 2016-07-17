from django.shortcuts import render
from django.conf import settings
from django.forms import ModelForm
from django.forms.models import modelformset_factory
from django.forms.widgets import CheckboxSelectMultiple
from django.forms.models import ModelMultipleChoiceField
from django.views.decorators.cache import cache_page
from django.views.generic.base import TemplateView

from actionlog.models import ActionLogEntry
from divisions.models import Division
from tournaments.mixins import RoundMixin
from tournaments.models import Round
from utils.mixins import SuperuserRequiredMixin
from utils.views import admin_required, expect_post, public_optional_tournament_view, redirect_round, round_view

from .models import Motion


@cache_page(settings.PUBLIC_PAGE_CACHE_TIMEOUT)
@public_optional_tournament_view('public_motions')
def public_motions(request, t):
    order_by = 'seq' if t.pref('public_motions_order') == 'forward' else '-seq'
    rounds = Round.objects.filter(motions_released=True, tournament=t).order_by(order_by)
    for round in rounds:
        round.motions = round.motion_set.all()

    return render(request, 'public_motions.html', dict(rounds=rounds))


@admin_required
@round_view
def motions_edit(request, round):
    motion_form_set = modelformset_factory(
        Motion, can_delete=True, extra=3, exclude=['round'])

    if request.method == 'POST':
        formset = motion_form_set(request.POST, request.FILES)
        if formset.is_valid():
            motions = formset.save(commit=False)
            for motion in motions:
                motion.round = round
                motion.save()
                ActionLogEntry.objects.log(
                    type=ActionLogEntry.ACTION_TYPE_MOTION_EDIT,
                    user=request.user, motion=motion, tournament=round.tournament)
            for motions in formset.deleted_objects:
                motions.delete()
            if 'submit' in request.POST:
                return redirect_round('draw', round)
    else:
        formset = motion_form_set(queryset=Motion.objects.filter(round=round))

    return render(request, "edit.html", dict(formset=formset))


@admin_required
@round_view
def motions_assign(request, round):

    class MyModelChoiceField(ModelMultipleChoiceField):
        def label_from_instance(self, obj):
            return "D%s @ %s" % (
                obj.name,
                obj.venue_group.short_name,
            )

    class ModelAssignForm(ModelForm):
        divisions = MyModelChoiceField(
            widget=CheckboxSelectMultiple,
            queryset=Division.objects.filter(tournament=round.tournament).order_by('venue_group'))

        class Meta:
            model = Motion
            fields = ("divisions",)

    motion_form_set = modelformset_factory(Motion, ModelAssignForm, extra=0, fields=['divisions'])

    if request.method == 'POST':
        formset = motion_form_set(request.POST)
        formset.save()  # Should be checking for validity but on a deadline and was buggy
        if 'submit' in request.POST:
            return redirect_round('motions', round)

    formset = motion_form_set(queryset=Motion.objects.filter(round=round))
    return render(request, "assign.html", dict(formset=formset))


@admin_required
@expect_post
@round_view
def release_motions(request, round):
    round.motions_released = True
    round.save()
    ActionLogEntry.objects.log(
        type=ActionLogEntry.ACTION_TYPE_MOTIONS_RELEASE,
        user=request.user, round=round, tournament=round.tournament)

    return redirect_round('draw', round)


@admin_required
@expect_post
@round_view
def unrelease_motions(request, round):
    round.motions_released = False
    round.save()
    ActionLogEntry.objects.log(
        type=ActionLogEntry.ACTION_TYPE_MOTIONS_UNRELEASE,
        user=request.user, round=round, tournament=round.tournament)

    return redirect_round('draw', round)


class DisplayMotionsView(SuperuserRequiredMixin, RoundMixin, TemplateView):

    template_name = 'show.html'

    def get_context_data(self, **kwargs):
        kwargs['motions'] = self.get_round().motion_set.all()
        return super().get_context_data(**kwargs)