import django_filters

from .models import Beat


class BeatFilter(django_filters.FilterSet):
    genre = django_filters.CharFilter(lookup_expr="iexact")
    key = django_filters.CharFilter(lookup_expr="iexact")
    bpm_min = django_filters.NumberFilter(field_name="bpm", lookup_expr="gte")
    bpm_max = django_filters.NumberFilter(field_name="bpm", lookup_expr="lte")
    tag = django_filters.CharFilter(method="filter_tag")

    class Meta:
        model = Beat
        fields = ["genre", "key", "bpm_min", "bpm_max", "tag"]

    def filter_tag(self, queryset, name, value):
        return queryset.filter(tags__contains=[value])
