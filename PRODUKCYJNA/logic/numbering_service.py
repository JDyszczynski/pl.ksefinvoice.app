from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, desc, asc
from database.models import Invoice, NumberingSetting, PeriodType, InvoiceCategory, InvoiceType
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class NumberingException(Exception):
    pass

class NumberingService:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_config(self, category: InvoiceCategory, type: InvoiceType) -> NumberingSetting:
        """Pobiera konfigurację numeracji dla danego typu dokumentu lub tworzy domyślną."""
        setting = self.session.query(NumberingSetting).filter_by(
            invoice_category=category,
            invoice_type=type
        ).first()

        if not setting:
            # Utwórz domyślną
            logger.info(f"Creating default config for {category} - {type}")
            setting = NumberingSetting(
                invoice_category=category,
                invoice_type=type,
                period_type=PeriodType.YEARLY,
                template="{nr}/{rok}" if category == InvoiceCategory.SALES else "KOR/{nr}/{rok}"
            )
            self.session.add(setting)
            self.session.commit()
            self.session.refresh(setting)
        
        return setting

    def check_period_validity(self, target_date: datetime):
        """Sprawdza czy data nie wybiega w przyszłość (nie rozpoczęty rok/miesiąc)."""
        now = datetime.now()
        
        # Jeśli rok daty > obecny rok -> Błąd
        if target_date.year > now.year:
             raise NumberingException(f"Nie można wystawić faktury na rok {target_date.year}, który się jeszcze nie rozpoczął.")
        
        # Jeśli ten sam rok, ale miesiąc > obecny -> Błąd
        if target_date.year == now.year and target_date.month > now.month:
             raise NumberingException(f"Nie można wystawić faktury na miesiąc {target_date.month}, który się jeszcze nie rozpoczął.")

    def find_potential_number(self, setting: NumberingSetting, target_date: datetime) -> int:
        """
        Znajduje numer dla danej daty.
        Algorytm:
        1. Sprawdza luki w numeracji dla danego okresu (rok/miesiąc).
        2. Dla każdej luki sprawdza, czy 'target_date' mieści się logicznie między fakturą przed i po luce.
        3. Jeśli nie ma pasującej luki, zwraca MAX + 1 (pod warunkiem zachowania chronologii).
        """
        
        # 1. Ustal zakres filtracji (Rok lub Rok+Miesiąc)
        # Determine types to include (Merge VAT and RYCZALT for Sales)
        types_to_include = [setting.invoice_type]
        if setting.invoice_category == InvoiceCategory.SALES:
             if setting.invoice_type in (InvoiceType.VAT, InvoiceType.RYCZALT):
                  types_to_include = [InvoiceType.VAT, InvoiceType.RYCZALT]

        query = self.session.query(Invoice).filter(
            Invoice.category == setting.invoice_category,
            Invoice.type.in_(types_to_include),
            Invoice.sequence_year == target_date.year
        )
        
        if setting.period_type == PeriodType.MONTHLY:
            query = query.filter(Invoice.sequence_month == target_date.month)
            
        # Pobierz wszystkie istniejące numery i daty wystawienia, posortowane rosnąco
        existing_invoices = query.with_entities(
            Invoice.sequence_number, Invoice.date_issue
        ).order_by(Invoice.sequence_number.asc()).all()
        
        # Jeśli brak faktur w tym okresie -> Numer 1
        if not existing_invoices:
            return 1
            
        # 2. Szukanie luk
        # existing_invoices to lista krotek (number, date)
        # Przygotuj mapę numer -> data
        inv_map = {inv.sequence_number: inv.date_issue for inv in existing_invoices}
        max_num = existing_invoices[-1].sequence_number
        
        # Sprawdzamy każdą potencjalną lukę od 1 do max_num
        # (Teoretycznie luką może być też 1)
        for cand_num in range(1, max_num):
            if cand_num not in inv_map:
                # Mamy lukę nr 'cand_num'. Sprawdźmy sąsiedztwo.
                # Poprzednik: cand_num - 1 (jeśli cand_num=1, brak poprzednika)
                # Następnik: cand_num + 1 (musi istnieć, bo iterujemy do max_num)
                # Ale uwaga: może być luka wielopoziomowa (np. brak 2, 3). Znajdźmy najbliższego istniejącego sąsiada.
                
                prev_date = None
                # Szukaj poprzednika
                p = cand_num - 1
                while p > 0:
                    if p in inv_map:
                        prev_date = inv_map[p]
                        break
                    p -= 1
                    
                # Szukaj następnika
                next_date = None
                n = cand_num + 1
                while n <= max_num:
                    if n in inv_map:
                        next_date = inv_map[n]
                        break
                    n += 1
                

                # Walidacja daty dla luki
                # Warunek: prev_date <= target_date <= next_date
                # Jeśli prev_date is None (wstawiamy nr 1), to target_date <= next_date
                
                # Normalizuj daty do datetime.date
                t_date = target_date.date() if hasattr(target_date, 'date') else target_date
                p_date = prev_date.date() if prev_date and hasattr(prev_date, 'date') else prev_date
                n_date = next_date.date() if next_date and hasattr(next_date, 'date') else next_date
                
                valid_gap = True
                if p_date and t_date < p_date:
                    valid_gap = False
                if n_date and t_date > n_date:
                    valid_gap = False
                    
                if valid_gap:
                    logger.info(f"Found valid gap: {cand_num} for date {target_date}")
                    return cand_num
                    
        # 3. Brak pasujących luk (lub brak luk w ogóle).
        # Numer to Max + 1.
        # Sprawdź chronologię: target_date >= data ostatniej faktury.
        
        last_invoice_date = existing_invoices[-1].date_issue
        
        # Normalizuj
        t_date = target_date.date() if hasattr(target_date, 'date') else target_date
        l_date = last_invoice_date.date() if hasattr(last_invoice_date, 'date') else last_invoice_date
        
        if t_date < l_date:
            raise NumberingException(
                f"Data wystawienia ({t_date}) nie może być wcześniejsza "
                f"niż data ostatniej faktury nr {max_num} ({l_date}). "
                "Brak dostępnych luk w numeracji pozwalających na tę datę."
            )
            
        return max_num + 1

    def format_number(self, setting: NumberingSetting, seq_num: int, date: datetime) -> str:
        """Formatuje numer wg wzorca."""
        # Wzorzec np: "{nr}/{rok}" lub "FV/{nr}/{mm}/{rok}"
        
        s = setting.template
        s = s.replace("{nr}", str(seq_num))
        s = s.replace("{rok}", str(date.year))
        s = s.replace("{miesiac}", f"{date.month:02d}")
        s = s.replace("{mm}", f"{date.month:02d}") # alias
        
        return s

    def get_number_parts(self, setting: NumberingSetting, date: datetime) -> tuple[str, str]:
        """Zwraca prefix i suffix dla pola edycji numeru."""
        s = setting.template
        parts = s.split("{nr}")
        prefix = parts[0]
        suffix = parts[1] if len(parts) > 1 else ""
        
        # Replace date placeholders
        for i, p in enumerate([prefix, suffix]):
            p = p.replace("{rok}", str(date.year))
            p = p.replace("{miesiac}", f"{date.month:02d}")
            p = p.replace("{mm}", f"{date.month:02d}")
            if i == 0: prefix = p
            else: suffix = p
            
        return prefix, suffix

    def apply_numbering(self, invoice: Invoice, manual_sequence_number: int = None):
        """
        Metoda główna do nadawania numeru fakturze (działa in-place na obiekcie Invoice).
        manual_sequence_number: Opcjonalny wymuszony numer kolejny.
        """
        if not invoice.category or not invoice.type or not invoice.date_issue:
            raise ValueError("Invoice requires category, type and date_issue to be numbered.")
            
        # 1. Pobierz konfigurację
        setting = self.get_or_create_config(invoice.category, invoice.type)
        
        # 2. Sprawdź czy okres nie jest z przyszłości
        self.check_period_validity(invoice.date_issue)
        
        if manual_sequence_number is not None:
             # Jeśli podano ręcznie, używamy go (ewentualnie można tu dodać walidację czy numer nie jest zajęty)
             # Sprawdź unikalność
             q = self.session.query(Invoice).filter(
                Invoice.category == setting.invoice_category,
                Invoice.type == setting.invoice_type,
                Invoice.sequence_year == invoice.date_issue.year,
                Invoice.sequence_number == manual_sequence_number
             )
             if setting.period_type == PeriodType.MONTHLY:
                 q = q.filter(Invoice.sequence_month == invoice.date_issue.month)
             
             if q.first():
                 raise NumberingException(f"Numer {manual_sequence_number} jest już zajęty w tym okresie.")
             
             seq_num = manual_sequence_number
        else:
            # 3. Znajdź numer (seq_number) automatycznie
            seq_num = self.find_potential_number(setting, invoice.date_issue)
        
        # 4. Ustaw pola na fakturze
        invoice.sequence_number = seq_num
        invoice.sequence_year = invoice.date_issue.year
        if setting.period_type == PeriodType.MONTHLY:
            invoice.sequence_month = invoice.date_issue.month
        else:
            invoice.sequence_month = None
            
        # 5. Zgeneruj pełny string numeru
        full_number = self.format_number(setting, seq_num, invoice.date_issue)
        invoice.number = full_number
        
        return full_number
