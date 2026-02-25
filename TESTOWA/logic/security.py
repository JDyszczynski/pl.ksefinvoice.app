import base64
import uuid
import hashlib
import platform
from cryptography.fernet import Fernet

class SecurityManager:
    _key = None

    @classmethod
    def _get_key(cls):
        """
        Generuje klucz szyfrowania powiązany z bieżącą maszyną.
        Zabezpiecza to przed odszyfrowaniem bazy na innym komputerze (w przypadku wycieku pliku .db).
        """
        if cls._key is None:
            # Unikalny identyfikator maszyny (MAC address + Hostname + Machine Type)
            # Uwaga: uuid.getnode() może zwrócić losową wartość jeśli brak interfejsów sieciowych,
            # ale w typowym środowisku desktop jest stabilny.
            machine_id = str(uuid.getnode()) + platform.node() + platform.machine()
            
            # Application specific salt
            salt = "KsefInvoice_Secure_Salt_v1" 
            
            # SHA256 -> 32 bytes
            full_key = hashlib.sha256((machine_id + salt).encode()).digest()
            
            # Fernet wymaga 32-bajtowego klucza w base64 url-safe
            cls._key = base64.urlsafe_b64encode(full_key)
            
        return cls._key

    @staticmethod
    def encrypt(text: str) -> str:
        """Szyfruje tekst (hasło)"""
        if not text: return None
        try:
            f = Fernet(SecurityManager._get_key())
            # Fernet encrypt returns bytes, decode to store as string
            return f.encrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"Błąd szyfrowania: {e}")
            return None

    @staticmethod
    def decrypt(token: str) -> str:
        """Odszyfrowuje token"""
        if not token: return None
        try:
            f = Fernet(SecurityManager._get_key())
            return f.decrypt(token.encode('utf-8')).decode('utf-8')
        except Exception as e:
            # Jeśli nie uda się odszyfrować (np. inna maszyna, uszkodzone dane)
            # Zwracamy None, co wymusi na użytkowniku ponowne wprowadzenie hasła
            print(f"Błąd deszyfrowania (możliwa zmiana maszyny): {e}")
            return None
