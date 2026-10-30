from odoo.orm.domains import Domain


def formatted_read_group_with_dynamic_sums(
    records, call_super, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None,
    dynamic_sums=(),
):
    """Keep context-dependent accrual values available in grouped list views."""
    dynamic_sums = set(dynamic_sums)
    requested_dynamic_sums = [spec for spec in aggregates if spec in dynamic_sums]
    regular_aggregates = [spec for spec in aggregates if spec not in dynamic_sums]
    groups = call_super(domain, groupby, regular_aggregates, having, offset, limit, order)
    if not requested_dynamic_sums:
        return groups

    for group in groups:
        group_domain = Domain(domain)
        if group.get("__extra_domain"):
            group_domain &= Domain(group["__extra_domain"])
        group_records = records.search(group_domain)
        for aggregate_spec in requested_dynamic_sums:
            field_name = aggregate_spec.rsplit(":", 1)[0]
            group[aggregate_spec] = sum(group_records.mapped(field_name))
    return groups
