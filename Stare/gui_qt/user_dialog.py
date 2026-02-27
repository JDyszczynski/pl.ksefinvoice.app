from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
                             QCheckBox, QPushButton, QHBoxLayout, QMessageBox, QLabel)
import hashlib

class UserDialog(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Użytkownik" if not user else f"Edycja {user.username}")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.username_edit = QLineEdit()
        if self.user:
            self.username_edit.setText(self.user.username)
            # self.username_edit.setReadOnly(True) # Optionally disable renaming
        form.addRow("Nazwa:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Pozostaw puste, aby nie zmieniać/nie ustawiać")
        form.addRow("Hasło:", self.password_edit)

        # Checkboxes
        self.chk_send = QCheckBox("Wysyłanie do KSeF")
        self.chk_recv = QCheckBox("Odbieranie z KSeF")
        self.chk_settle = QCheckBox("Dostęp do Rozliczeń")
        self.chk_decl = QCheckBox("Dostęp do Deklaracji")
        self.chk_settings = QCheckBox("Dostęp do Konfiguracji")

        if self.user:
            self.chk_send.setChecked(self.user.perm_send_ksef or False)
            self.chk_recv.setChecked(self.user.perm_receive_ksef or False)
            self.chk_settle.setChecked(self.user.perm_settlements or False)
            self.chk_decl.setChecked(self.user.perm_declarations or False)
            self.chk_settings.setChecked(self.user.perm_settings or False)

        layout.addLayout(form)
        layout.addWidget(QLabel("Uprawnienia:"))
        layout.addWidget(self.chk_send)
        layout.addWidget(self.chk_recv)
        layout.addWidget(self.chk_settle)
        layout.addWidget(self.chk_decl)
        layout.addWidget(self.chk_settings)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Zapisz")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Anuluj")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def get_data(self):
        return {
            "username": self.username_edit.text(),
            "password": self.password_edit.text(),
            "perm_send_ksef": self.chk_send.isChecked(),
            "perm_receive_ksef": self.chk_recv.isChecked(),
            "perm_settlements": self.chk_settle.isChecked(),
            "perm_declarations": self.chk_decl.isChecked(),
            "perm_settings": self.chk_settings.isChecked()
        }
