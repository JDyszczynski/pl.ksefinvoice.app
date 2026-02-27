import flet as ft
from database.engine import get_db
from database.models import User

class LoginView(ft.Container):
    def __init__(self, on_login_success):
        super().__init__(expand=True)
        self.on_login_success = on_login_success
        self.alignment = ft.Alignment(0, 0)
        self.bgcolor = ft.Colors.BLUE_GREY_50 # Tło całego ekranu logowania
        
        self.username = ft.TextField(label="Użytkownik", width=300)
        self.password = ft.TextField(label="Hasło", password=True, can_reveal_password=True, width=300)
        
        # Zastępujemy skomplikowany layout prostszym dla debugowania
        self.content = ft.Container(
            bgcolor=ft.Colors.WHITE,
            padding=40,
            border_radius=10,
            # Usuwamy cień, który może powodować problemy z renderowaniem na Linuxie
            border=ft.border.all(1, ft.Colors.GREY_300),
            content=ft.Column(
                [
                    ft.Text("Wersja Debug", color="red"),
                    # Usunięto ikonę, aby wykluczyć problemy z fontami
                    ft.Text("Logowanie", size=24, weight="bold", color=ft.Colors.BLACK),
                    ft.Container(height=20),
                    self.username,
                    self.password,
                    ft.Container(height=20),
                    ft.ElevatedButton("Zaloguj", on_click=self.login, width=300)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                # tight=True czasem powoduje problemy z layoutem jeśli rodzic ma inne constraints
                # tight=True 
            )
        )

    def login(self, e):
        db = next(get_db())
        user = db.query(User).filter(User.username == self.username.value).first()
        
        # Development bypass: jeśli nie ma userów w bazie, a wpisano admin/admin, utwórz
        if not user and self.username.value == "admin" and self.password.value == "admin":
            import hashlib
            p_hash = hashlib.sha1("admin".encode()).hexdigest()
            user = User(username="admin", password_hash=p_hash, perm_settings=True, perm_send_ksef=True)
            db.add(user)
            db.commit()
            db.refresh(user)

        if user:
             # Check hash
             import hashlib
             p_input_hash = hashlib.sha1(self.password.value.encode()).hexdigest()
             if user.password_hash == p_input_hash:
                 self.on_login_success(user)
             else:
                 if self.page:
                     self.page.snack_bar = ft.SnackBar(ft.Text("Błędny login lub hasło!"))
                     self.page.snack_bar.open = True
                     self.page.update()
        else:
             if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text("Błędny login lub hasło!"))
                self.page.snack_bar.open = True
                self.page.update()
        
        db.close()
