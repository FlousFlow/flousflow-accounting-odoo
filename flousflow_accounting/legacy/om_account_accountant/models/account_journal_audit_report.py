from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class AccountJournalAuditReport(models.AbstractModel):
    _name = "account.journal.audit.report"
    _description = "Interactive Journal Audit Report"

    _REVIEW_LABELS = {
        "no_review": "No Review",
        "todo": "To Review",
        "anomaly": "Anomaly",
        "reviewed": "Reviewed",
        "supervised": "Supervised",
    }

    @api.model
    def get_fiscal_year_range(self, anchor_date=None):
        """Return the active company's fiscal-year bounds around a selected date."""
        anchor_date = fields.Date.to_date(anchor_date) or fields.Date.context_today(self)
        dates = self.env.company.compute_fiscalyear_dates(anchor_date)
        return {
            "date_from": fields.Date.to_string(dates["date_from"]),
            "date_to": fields.Date.to_string(dates["date_to"]),
        }

    @api.model
    def _get_report_filters(self, date_from, date_to, target_move, include_payments=False):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to or date_from > date_to:
            raise ValidationError(_("Choose a valid date range."))
        if target_move not in ("posted", "draft", "all"):
            raise ValidationError(_("Unsupported journal entry filter."))

        move_domain = [
            ("company_id", "=", self.env.company.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("state", "!=", "cancel"),
        ]
        line_domain = [
            ("company_id", "=", self.env.company.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("parent_state", "!=", "cancel"),
        ]
        if target_move == "posted":
            move_domain.append(("state", "=", "posted"))
            line_domain.append(("parent_state", "=", "posted"))
        elif target_move == "draft":
            move_domain.append(("state", "=", "draft"))
            line_domain.append(("parent_state", "=", "draft"))
        if not include_payments:
            move_domain.append(("origin_payment_id", "=", False))
            line_domain.append(("move_id.origin_payment_id", "=", False))
        return date_from, date_to, move_domain, line_domain

    @api.model
    def get_report_data(self, date_from, date_to, target_move="posted", include_payments=False):
        """Return a company-scoped journal and tax summary using the current user's rights."""
        date_from, date_to, move_domain, line_domain = self._get_report_filters(
            date_from, date_to, target_move, include_payments
        )
        move_groups = self.env["account.move"]._read_group(
            move_domain, ["journal_id", "move_type", "review_state"], ["__count"]
        )
        move_type_labels = dict(self.env["account.move"]._fields["move_type"]._description_selection(self.env))
        journals = {}
        for journal, move_type, review_state, count in move_groups:
            if not journal:
                continue
            group_key = f"{journal.id}:{move_type}"
            row = journals.setdefault(group_key, {
                "id": group_key,
                "journal_id": journal.id,
                "name": journal.display_name,
                "move_type": move_type,
                "document_type": self._get_document_type_label(move_type, move_type_labels),
                "documents": 0,
                "to_review": 0,
                "debit": 0.0,
                "credit": 0.0,
                "balance": 0.0,
                "accounts": [],
                "taxes": {},
            })
            row["documents"] += count
            if review_state in ("todo", "anomaly"):
                row["to_review"] += count

        move_types = {row["move_type"] for row in journals.values()}
        for move_type in move_types:
            line_groups = self.env["account.move.line"]._read_group(
                line_domain + [("move_id.move_type", "=", move_type)],
                ["journal_id", "account_id"],
                ["debit:sum", "credit:sum", "balance:sum"],
            )
            for journal, account, debit, credit, balance in line_groups:
                if not journal or not account:
                    continue
                row = journals.get(f"{journal.id}:{move_type}")
                if not row:
                    continue
                debit, credit, balance = debit or 0.0, credit or 0.0, balance or 0.0
                row["debit"] += debit
                row["credit"] += credit
                row["balance"] += balance
                row["accounts"].append({
                    "account_id": account.id,
                    "code": account.code or "",
                    "name": account.display_name,
                    "debit": debit,
                    "credit": credit,
                    "balance": balance,
                })

        grouped_tax_lines = self.env["account.move.line"]._read_group(
            line_domain + [("tax_line_id", "!=", False)],
            ["journal_id", "move_id", "tax_line_id"],
            ["tax_base_amount:sum", "debit:sum", "credit:sum", "balance:sum"],
        )
        for journal, move, tax, base, debit, credit, balance in grouped_tax_lines:
            if not journal or not move or not tax:
                continue
            row = journals.get(f"{journal.id}:{move.move_type}")
            if not row:
                continue
            tax_row = row["taxes"].setdefault(tax.id, {
                "id": tax.id,
                "name": tax.display_name,
                "base": 0.0,
                "debit": 0.0,
                "credit": 0.0,
                "balance": 0.0,
            })
            tax_row["base"] += base or 0.0
            tax_row["debit"] += debit or 0.0
            tax_row["credit"] += credit or 0.0
            tax_row["balance"] += balance or 0.0

        tax_groups = self.env["account.move.line"]._read_group(
            line_domain + [("tax_line_id", "!=", False)],
            ["tax_line_id"],
            ["tax_base_amount:sum", "debit:sum", "credit:sum", "balance:sum"],
        )
        taxes = [
            {
                "id": tax.id,
                "name": tax.display_name,
                "base": base or 0.0,
                "debit": debit or 0.0,
                "credit": credit or 0.0,
                "balance": balance or 0.0,
            }
            for tax, base, debit, credit, balance in tax_groups
            if tax
        ]

        for row in journals.values():
            row["taxes"] = sorted(row["taxes"].values(), key=lambda tax: tax["name"].casefold())

        currency = self.env.company.currency_id
        return {
            "journals": sorted(journals.values(), key=lambda row: (row["name"].casefold(), row["document_type"].casefold())),
            "taxes": taxes,
            "currency_id": currency.id,
            "company_id": self.env.company.id,
            "company_name": self.env.company.display_name,
            "can_audit": self.env.user.has_group("account.group_account_user")
            or self.env.user.has_group("account.group_account_manager"),
        }

    @api.model
    def _get_document_type_label(self, move_type, move_type_labels):
        if move_type in ("in_invoice", "out_invoice"):
            return _("Invoice")
        if move_type in ("in_refund", "out_refund"):
            return _("Credit Note")
        return move_type_labels.get(move_type, move_type)

    @api.model
    def get_journal_moves(self, journal_id, date_from, date_to, target_move="posted", include_payments=False, offset=0, limit=100):
        """Load one page of journal documents for an expanded report row."""
        date_from, date_to, move_domain, _line_domain = self._get_report_filters(
            date_from, date_to, target_move, include_payments
        )
        journal = self.env["account.journal"].browse(int(journal_id)).exists()
        if not journal or journal.company_id != self.env.company:
            raise AccessError(_("The selected journal is outside the active company."))
        move_domain.append(("journal_id", "=", journal.id))
        offset = max(0, int(offset))
        limit = min(max(1, int(limit)), 200)
        moves = self.env["account.move"].search(
            move_domain, order="date, name, id", offset=offset, limit=limit + 1
        )
        has_more = len(moves) > limit
        moves = moves[:limit]
        line_totals = {}
        if moves:
            for move, debit, credit, balance in self.env["account.move.line"]._read_group(
                [("move_id", "in", moves.ids)],
                ["move_id"],
                ["debit:sum", "credit:sum", "balance:sum"],
            ):
                if move:
                    line_totals[move.id] = (debit or 0.0, credit or 0.0, balance or 0.0)

        move_type_labels = dict(
            self.env["account.move"]._fields["move_type"]._description_selection(self.env)
        )
        return {
            "rows": [
                {
                    "id": move.id,
                    "date": fields.Date.to_string(move.date),
                    "name": move.name,
                    "ref": move.ref or "",
                    "document_type": move_type_labels.get(move.move_type, move.move_type),
                    "state": move.state,
                    "review_state": self._REVIEW_LABELS.get(move.review_state, move.review_state),
                    "debit": line_totals.get(move.id, (0.0, 0.0, 0.0))[0],
                    "credit": line_totals.get(move.id, (0.0, 0.0, 0.0))[1],
                    "balance": line_totals.get(move.id, (0.0, 0.0, 0.0))[2],
                }
                for move in moves
            ],
            "offset": offset + len(moves),
            "has_more": has_more,
        }

    @api.model
    def mark_journal_reviewed(self, journal_id, date_from, date_to, include_payments=False, move_type=None):
        """Mark only posted entries still awaiting review in this journal and period."""
        if not (
            self.env.user.has_group("account.group_account_user")
            or self.env.user.has_group("account.group_account_manager")
        ):
            raise AccessError(_("Only accounting users can mark journal entries as reviewed."))
        _date_from, _date_to, move_domain, _line_domain = self._get_report_filters(
            date_from, date_to, "posted", include_payments
        )
        journal = self.env["account.journal"].browse(int(journal_id)).exists()
        if not journal or journal.company_id != self.env.company:
            raise AccessError(_("The selected journal is outside the active company."))
        move_domain += [
            ("journal_id", "=", journal.id),
            ("review_state", "in", ["todo", "anomaly"]),
        ]
        if move_type:
            valid_move_types = dict(self.env["account.move"]._fields["move_type"]._description_selection(self.env))
            if move_type not in valid_move_types:
                raise ValidationError(_("Unsupported document type."))
            move_domain.append(("move_type", "=", move_type))
        moves = self.env["account.move"].search(move_domain)
        count = len(moves)
        moves.set_moves_checked()
        return count
