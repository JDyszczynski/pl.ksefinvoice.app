from database.engine import get_db
from database.models import User

def fix_admin():
    db = next(get_db())
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if user:
            print(f"Znaleziono użytkownika: {user.username}")
            user.perm_send_ksef = True
            user.perm_receive_ksef = True
            user.perm_settlements = True
            user.perm_declarations = True
            user.perm_settings = True
            db.commit()
            print("Nadano wszystkie uprawnienia użytkownikowi 'admin'.")
        else:
            print("Nie znaleziono użytkownika 'admin' w bazie danych.")
    except Exception as e:
        print(f"Wystąpił błąd: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fix_admin()
