from database.engine import engine
from database.models import Base

def db_update():
    print("Updating database schema...")
    Base.metadata.create_all(engine)
    print("Database schema updated.")

if __name__ == "__main__":
    db_update()
