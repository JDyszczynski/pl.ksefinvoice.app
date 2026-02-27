from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QMessageBox, QFrame, QComboBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from database.engine import get_db
from database.models import User
from gui_qt.resource_path import resource_path
import traceback
import hashlib

class LoginView(QWidget):
    def __init__(self, on_success_callback, version_string=None):
        super().__init__()
        self.on_success = on_success_callback
        self.version_string = version_string
        self.init_ui()
        self.load_users()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        self.setLayout(layout)

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFixedWidth(400)
        frame_layout = QVBoxLayout(frame)
        
        # Logo
        logo_label = QLabel()
        logo_path = resource_path("logo.ico")
        logo_pixmap = QPixmap(logo_path)
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
            frame_layout.addWidget(logo_label)

        # Header
        app_title = QLabel("KSeF Invoice Polska")
        app_title.setAlignment(Qt.AlignCenter)
        app_title.setStyleSheet("font-size: 32px; font-weight: bold; color: #1976D2; margin-bottom: 5px;")
        frame_layout.addWidget(app_title)

        if self.version_string:
            version_label = QLabel(f"Wersja: {self.version_string}")
            version_label.setAlignment(Qt.AlignCenter)
            version_label.setStyleSheet("color: #666; font-size: 14px; margin-bottom: 20px;")
            frame_layout.addWidget(version_label)
        else:
            frame_layout.addSpacing(20)

        title = QLabel("Logowanie")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px;")
        
        # User Selection ComboBox or LineEdit
        self.user_combo = QComboBox()
        self.user_combo.setPlaceholderText("Wybierz użytkownika")
        self.user_combo.currentIndexChanged.connect(self.on_user_changed)
        
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Wprowadź nazwę użytkownika")
        self.user_input.hide()

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Hasło (opcjonalne)")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.attempt_login)

        self.login_btn = QPushButton("Zaloguj")
        self.login_btn.setStyleSheet("padding: 10px; background-color: #2196F3; color: white; font-weight: bold;")
        self.login_btn.clicked.connect(self.attempt_login)

        frame_layout.addWidget(title)
        frame_layout.addWidget(QLabel("Użytkownik:"))
        frame_layout.addWidget(self.user_combo)
        frame_layout.addWidget(self.user_input)
        frame_layout.addWidget(QLabel("Hasło:"))
        frame_layout.addWidget(self.password_input)
        frame_layout.addSpacing(20)
        frame_layout.addWidget(self.login_btn)

        layout.addWidget(frame)

    def load_users(self):
        db = next(get_db())
        try:
            users = db.query(User).all()
            self.user_combo.clear()
            
            if not users:
                self.user_combo.hide()
                self.user_input.show()
                self.is_first_run = True
            else:
                self.user_combo.show()
                self.user_input.hide()
                self.is_first_run = False
                for user in users:
                    self.user_combo.addItem(user.username, user.id)
                
                if self.user_combo.count() > 0:
                    self.user_combo.setCurrentIndex(0)

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Błąd", f"Błąd ładowania użytkowników: {e}")
        finally:
            db.close()

    def on_user_changed(self, index):
        self.password_input.clear()

    def reset(self):
        self.user_input.clear()
        self.password_input.clear()
        self.load_users()

    def attempt_login(self):
        if self.is_first_run:
            self.handle_first_run_login()
            return
            
        selected_user_id = self.user_combo.currentData()
        password = self.password_input.text()
        
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == selected_user_id).first()
            
            if not user:
                QMessageBox.error(self, "Błąd", "Nie znaleziono użytkownika.")
                return

            if user.password_hash:
                input_hash = hashlib.sha1(password.encode('utf-8')).hexdigest()
                if input_hash == user.password_hash:
                    self.on_success(user)
                else:
                    QMessageBox.warning(self, "Błąd", "Nieprawidłowe hasło")
            else:
                # No password required
                self.on_success(user)

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Błąd", f"Błąd logowania: {e}")
        finally:
            db.close()
            
    def handle_first_run_login(self):
        username = self.user_input.text().strip()
        password = self.password_input.text()
        
        if not username:
            QMessageBox.warning(self, "Błąd", "Podaj nazwę użytkownika.")
            return
            
        db = next(get_db())
        try:
            new_user = User(
                username=username, 
                password_hash=hashlib.sha1(password.encode('utf-8')).hexdigest() if password else None,
                # Give all permissions to first user
                perm_send_ksef=True,
                perm_receive_ksef=True,
                perm_settlements=True,
                perm_declarations=True,
                perm_settings=True
            )
            db.add(new_user)
            db.commit()
            QMessageBox.information(self, "Info", f"Utworzono użytkownika {username}.")
            self.on_success(new_user)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Błąd tworzenia użytkownika: {e}")
        finally:
            db.close()
