from sqlalchemy import func, extract
from sqlalchemy.orm import Session
from database.models import Invoice, InvoiceItem, InvoiceCategory, InvoiceType, CompanyConfig
from datetime import datetime
import logging

class RevenueService:
    def __init__(self, session: Session):
        self.session = session
        self.logger = logging.getLogger(__name__)

    def get_ytd_revenue(self, year: int = None) -> float:
        """
        Oblicza wartość sprzedaży (przychodu) narastająco od początku roku.
        Dla celów limitu VAT (Art. 113) liczy się wartość sprzedaży netto.
        Jeśli podatnik zwolniony - wartość sprzedaży (często brutto = netto).
        Liczymy sumę total_net faktur Sprzedaży (SALES).
        Tylko faktury nie będące zaliczkami? (W uproszczeniu wszystkie sprzedażowe).
        """
        if not year:
            year = datetime.now().year
            
        # Sum total_net from Sales Invoices
        # Filter: category=SALES, date_issue.year=year
        # Exclude drafts? Assuming all in DB are valid unless specific status exists.
        
        result = self.session.query(func.sum(Invoice.total_net)).filter(
            Invoice.category == InvoiceCategory.SALES,
            extract('year', Invoice.date_issue) == year,
            # Exclude corrections that might double count? 
            # Corrections adjust revenue. If KOREKTA, total_net might be negative (if reducing) or positive.
            # So simple sum should work correctly if data is correct.
        ).scalar()
        
        return result or 0.0

    def _get_period_sales_breakdown(self, year: int, month: int, is_vat_payer: bool = True):
        """
        Calculates Sales breakdown for a period, correctly handling CORRECTIONS (Delta).
        Total = Normal_Invoices + (Correction_New_State - Corrected_Parent_Old_State)
        """
        # 1. Sum Normal Invoices (Not KOREKTA)
        # Always use Net Price * Quantity as 'Net' base.
        # For non-VAT payers, Net usually equals Gross (Rate 0).
        # Typically PPE revenue is Net for VAT payers and Gross for Exempt.
        # However, if Exempt user issues invoices with VAT (mistake or historic), 
        # using Net ensures consistency if they expect tax calculation on Net.
        # If they issue correctly (Rate 0), Net == Gross, so this is safe.
        col_net = InvoiceItem.net_price * InvoiceItem.quantity
        col_gross = InvoiceItem.gross_value
        
        # Helper to query items
        def query_items(filter_conds):
            q = self.session.query(
                InvoiceItem.vat_rate,
                InvoiceItem.lump_sum_rate, 
                func.sum(col_net).label("net"),
                func.sum(col_gross).label("gross")
            ).join(Invoice).filter(
                Invoice.category == InvoiceCategory.SALES,
                extract('year', Invoice.date_issue) == year,
                extract('month', Invoice.date_issue) == month,
                *filter_conds
            ).group_by(InvoiceItem.vat_rate, InvoiceItem.lump_sum_rate).all()
            return q

        # A. Normal Invoices
        normal_data = query_items([Invoice.type != InvoiceType.KOREKTA])
        
        # B. Correction Invoices (The "New State" stored in DB)
        corrections_data = query_items([Invoice.type == InvoiceType.KOREKTA])
        
        # C. Corrected Invoices (The "Old State" that needs subtraction)
        # We need to find Invoices referenced by corrections in this period
        # Subquery for parents (using Query object directly to avoid SAWarning about coercion)
        parents_subquery = self.session.query(Invoice.parent_id).filter(
            Invoice.category == InvoiceCategory.SALES,
            Invoice.type == InvoiceType.KOREKTA,
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        )
        
        # Sum items of these parents
        parents_data = self.session.query(
            InvoiceItem.vat_rate,
            InvoiceItem.lump_sum_rate,
            func.sum(col_net).label("net"),
            func.sum(col_gross).label("gross")
        ).join(Invoice).filter(
            Invoice.id.in_(parents_subquery)
        ).group_by(InvoiceItem.vat_rate, InvoiceItem.lump_sum_rate).all()

        # Combine Results
        # Key = (vat_rate, lump_rate)
        combined = {}
        
        def add_to_combined(dataset, factor=1.0):
            for r, l, n, g in dataset:
                key = (r, l)
                if key not in combined:
                    combined[key] = {"net": 0.0, "gross": 0.0}
                combined[key]["net"] += (float(n or 0) * factor)
                combined[key]["gross"] += (float(g or 0) * factor)

        add_to_combined(normal_data, 1.0)
        add_to_combined(corrections_data, 1.0)
        add_to_combined(parents_data, -1.0) # Subtract old state
        
        return combined

    def get_monthly_summary(self, year: int, month: int):
        """
        Zwraca dane do deklaracji PPE (Przychodów Ewidencjonowanych).
        Grupowanie po stawkach ryczałtu.
        """
        config = self.session.query(CompanyConfig).first()
        is_vat_payer = config.is_vat_payer if (config and config.is_vat_payer is not None) else True
        
        combined_data = self._get_period_sales_breakdown(year, month, is_vat_payer)
        
        summary = []
        total_rev = 0.0
        total_tax_rounded = 0.0

        # Group by Lump Rate
        grouped_by_lump = {}
        
        for (vat_r, lump_r), vals in combined_data.items():
            if lump_r is None: continue
            if lump_r not in grouped_by_lump:
                grouped_by_lump[lump_r] = 0.0
            
            # For PPE, revenue base is stored in 'net' of our helper (which is Net or Gross based on config)
            grouped_by_lump[lump_r] += vals["net"]
            
        for rate, revenue in grouped_by_lump.items():
            rev = revenue
            tax_due = rev * float(rate)
            tax_rounded = round(tax_due) 
            
            total_rev += rev
            total_tax_rounded += tax_rounded

            summary.append({
                "rate": rate,
                "revenue": rev,
                "tax_calculated": tax_due,
                "tax_due": tax_rounded
            })
            
        return {
            "total_revenue": total_rev,
            "total_tax_rounded": total_tax_rounded,
            "details": summary
        }
    
    def get_ytd_tax_summary(self, year: int, month_end: int):
        """
        Oblicza podatek należny od początku roku do danego miesiąca włącznie.
        """
        # Simplified: Loop through months or write complex YTD query. 
        # Looping is safer to reuse logic.
        total_rev = 0.0
        details = {}
        
        for m in range(1, month_end + 1):
             data = self.get_monthly_summary(year, m)
             total_rev += data["total_revenue"]
             for d in data["details"]:
                 r = d["rate"]
                 if r not in details: details[r] = 0.0
                 details[r] += d["tax_calculated"]
        
        return {
            "total_revenue": total_rev,
            "total_tax_exact": sum(details.values()),
            "total_tax_rounded": round(sum(details.values())),
            "details": details
        }

    def get_monthly_sales_stats(self, year: int, month: int):
        """
        Zwraca statystyki sprzedaży VAT/Netto/Brutto dla danego miesiąca,
        wraz z podziałem na stawki.
        """
        # Always VAT Payer logic for VAT Stats
        combined_data = self._get_period_sales_breakdown(year, month, is_vat_payer=True)

        details = {}
        calc_net = 0.0
        calc_gross = 0.0
        
        for (vat_r, lump_r), vals in combined_data.items():
            n_val = vals["net"]
            g_val = vals["gross"]
            v_val = g_val - n_val
            
            calc_net += n_val
            calc_gross += g_val
            
            rate_key = str(vat_r) if vat_r is not None else "Inne"
            
            if rate_key not in details:
                 details[rate_key] = {"net": 0.0, "gross": 0.0, "vat": 0.0}
            
            details[rate_key]["net"] += n_val
            details[rate_key]["gross"] += g_val
            details[rate_key]["vat"] += v_val
        
        return {
            "net": calc_net,
            "gross": calc_gross,
            "vat": calc_gross - calc_net,
            "rates": details
        }


    def get_vat_register_summary(self, year: int, month: int):
        """
        Zwraca szczegółowe dane do Rejestru VAT (Ewidencji):
        - Sprzedaż (Netto, VAT, Brutto) z podziałem na stawki
        - Zakup (Netto, VAT, Brutto)
        """
        # --- SALES ---
        combined_data = self._get_period_sales_breakdown(year, month, is_vat_payer=True)

        sales_total_net = 0.0
        sales_total_gross = 0.0
        sales_breakdown = {
            "0.23": {"net": 0.0, "vat": 0.0},
            "0.08": {"net": 0.0, "vat": 0.0},
            "0.05": {"net": 0.0, "vat": 0.0},
            "0.0":  {"net": 0.0, "vat": 0.0}, # zw, 0%
            "other": {"net": 0.0, "vat": 0.0}
        }

        for (vat_r, lump_r), vals in combined_data.items():
            n_val = vals["net"]
            g_val = vals["gross"]
            v_val = g_val - n_val
            
            sales_total_net += n_val
            sales_total_gross += g_val
            
            rate_float = float(vat_r) if vat_r is not None else 0.0
            
            # Categorize
            if abs(rate_float - 0.23) < 0.001:
                key = "0.23"
            elif abs(rate_float - 0.08) < 0.001:
                key = "0.08"
            elif abs(rate_float - 0.05) < 0.001:
                key = "0.05"
            elif rate_float == 0.0:
                key = "0.0"
            else:
                key = "other"
            
            sales_breakdown[key]["net"] += n_val
            sales_breakdown[key]["vat"] += v_val

        sales_total_vat = sales_total_gross - sales_total_net

        # --- PURCHASES (Need similar Delta logic? Only if Purchase Corrections exist) ---
        # Current logic: Sums all Purchase invoices. 
        # If Purchase Correction (KOREKTA) exists, does it have items?
        # Usually yes. We should apply same logic.
        
        # Check Purchase corrections
        # 1. Normal Purch
        purch_normal = self.session.query(
            func.sum(Invoice.total_net).label("net"),
            func.sum(Invoice.total_gross).label("gross")
        ).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
            Invoice.type != InvoiceType.KOREKTA,
            Invoice.type != InvoiceType.PODATEK, # Exclude tax payments
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        ).first()

        # 2. Correction Purch (New State)
        purch_corr = self.session.query(
            func.sum(Invoice.total_net).label("net"),
            func.sum(Invoice.total_gross).label("gross")
        ).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
            Invoice.type == InvoiceType.KOREKTA,
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        ).first()

        # 3. Corrected Parent (Old State)
        purch_parents_sub = self.session.query(Invoice.parent_id).filter(
            Invoice.category == InvoiceCategory.PURCHASE,
            Invoice.type == InvoiceType.KOREKTA,
            extract('year', Invoice.date_issue) == year,
            extract('month', Invoice.date_issue) == month
        )
        
        purch_old = self.session.query(
            func.sum(Invoice.total_net).label("net"),
            func.sum(Invoice.total_gross).label("gross")
        ).filter(
            Invoice.id.in_(purch_parents_sub)
        ).first()

        p_net = (float(purch_normal.net or 0)) + (float(purch_corr.net or 0)) - (float(purch_old.net or 0))
        p_gross = (float(purch_normal.gross or 0)) + (float(purch_corr.gross or 0)) - (float(purch_old.gross or 0))
        p_vat = p_gross - p_net

        return {
            "sales": {
                "net": sales_total_net,
                "vat": sales_total_vat,
                "gross": sales_total_gross,
                "breakdown": sales_breakdown
            },
            "purchases": {
                "net": p_net,
                "vat": p_vat,
                "gross": p_gross
            },
            "balance": {
                "vat_due": sales_total_vat - p_vat
            }
        }


    def check_vat_limit_status(self, current_revenue: float = None) -> dict:
        """
        Sprawdza status względem limitu VAT i progu ostrzegawczego.
        """
        config = self.session.query(CompanyConfig).first()
        if not config or config.is_vat_payer or config.vat_exemption_subject_based:
            return {"status": "OK", "message": ""}
            
        if current_revenue is None:
            current_revenue = self.get_ytd_revenue()
            
        limit = config.vat_exemption_limit or 200000
        warning_t = config.vat_warning_threshold or 180000
        
        if current_revenue >= limit:
            return {
                "status": "BLOCKED", 
                "message": f"Przekroczono limit zwolnienia z VAT ({limit:,.2f} zł). "
                           f"Obecna wartość sprzedaży: {current_revenue:,.2f} zł.\n"
                           "Musisz zarejestrować się jako czynny podatnik VAT i zmienić ustawienia firmy.",
                "current": current_revenue,
                "limit": limit
            }
        elif current_revenue >= warning_t:
            return {
                "status": "WARNING",
                "message": f"Uwaga! Zbliżasz się do limitu zwolnienia z VAT.\n"
                           f"Obecna wartość: {current_revenue:,.2f} zł.\n"
                           f"Próg ostrzegawczy: {warning_t:,.2f} zł.\n"
                           f"Limit ustawowy: {limit:,.2f} zł.",
                "current": current_revenue,
                "limit": limit
            }
            
        return {"status": "OK", "message": "", "current": current_revenue, "limit": limit}
