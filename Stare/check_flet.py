import flet as ft
import inspect

print("Flet version:", ft.version)
print("\nDropdown init signature:")
print(inspect.signature(ft.Dropdown.__init__))

import flet as ft
import inspect

print("ElevatedButton init signature:")
print(inspect.signature(ft.ElevatedButton.__init__))

try:
    btn = ft.ElevatedButton(bgcolor="green")
    print("ElevatedButton accepts bgcolor directly")
except Exception as e:
    print(f"ElevatedButton ERROR: {e}")
    # Check if style is needed
    try:
        btn = ft.ElevatedButton(style=ft.ButtonStyle(bgcolor={"sw": "green"}))
        print("ElevatedButton needs style")
    except:
        pass
