import os
from database.engine import init_db

if os.path.exists("ksef_invoice.db"):
    os.remove("ksef_invoice.db")
    print("Usunięto starą bazę danych.")

init_db()
print("Utworzono nową strukturę bazy danych zgodną z modelami.")
