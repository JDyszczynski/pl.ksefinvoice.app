import os
import base64
from cryptography.hazmat.primitives import serialization, hashes, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography import x509
import logging

logger = logging.getLogger(__name__)

class EncryptionManager:
    def __init__(self, public_key_path="ksef/public_key_demo.pem", public_key_content=None):
        self.public_key_path = public_key_path
        self.public_key_content = public_key_content # Bytes
        self.aes_key = None
        self.aes_iv = None
        self.encrypted_aes_key = None # Base64 encoded

    def load_public_key(self):
        data = None
        if self.public_key_content:
             data = self.public_key_content
        elif self.public_key_path and os.path.exists(self.public_key_path):
             with open(self.public_key_path, "rb") as key_file:
                 data = key_file.read()
        else:
             raise FileNotFoundError(f"Public key not provided (content empty and file not found: {self.public_key_path})")
        
        # Try loading
        try:
            return serialization.load_pem_public_key(data)
        except ValueError:
            # If it's a certificate, load cert and extract public key
            try:
                cert = x509.load_pem_x509_certificate(data)
                return cert.public_key()
            except Exception as e:
                 raise ValueError(f"Could not load key. Ensure it is a valid PEM public key or certificate. {e}")


    def initialize_session_keys(self):
        """Generates AES key and IV, and encrypts the AES key with KSeF Public Key."""
        # 1. Generate AES-256 Key (32 bytes)
        self.aes_key = os.urandom(32)
        # 2. Generate IV (16 bytes for CBC)
        self.aes_iv = os.urandom(16)
        
        # 3. Encrypt AES key using RSA Public Key
        public_key = self.load_public_key()
        encrypted_key_bytes = public_key.encrypt(
            self.aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        self.encrypted_aes_key = base64.b64encode(encrypted_key_bytes).decode('utf-8')
        
        return {
            "key": self.aes_key,
            "iv": self.aes_iv,
            "encrypted_key": self.encrypted_aes_key,
            "iv_base64": base64.b64encode(self.aes_iv).decode('utf-8')
        }

    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypts data using AES-256-CBC with PKCS7 padding."""
        if not self.aes_key or not self.aes_iv:
            raise ValueError("Session keys not initialized. Call initialize_session_keys first.")

        # Pad data
        padder = sym_padding.PKCS7(128).padder() # 128-bit block size for AES
        padded_data = padder.update(data) + padder.finalize()

        # Encrypt
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_iv))
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        
        return encrypted_data

    def encrypt_ksef_token(self, token: str, timestamp_ms: int) -> str:
        """Encrypts KSeF authorization token: token|timestamp."""
        msg = f"{token}|{timestamp_ms}".encode("utf-8")
        public_key = self.load_public_key()
        
        encrypted = public_key.encrypt(
            msg,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return base64.b64encode(encrypted).decode("utf-8")

