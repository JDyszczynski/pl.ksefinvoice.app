import flet as ft

def main(page: ft.Page):
    page.title = "Test Dropdown"

    def on_change(e):
        print("Dropdown changed to:", e.control.value)
        t.value = f"Selected: {e.control.value}"
        t.update()

    dd = ft.Dropdown(
        width=200,
        options=[
            ft.dropdown.Option("A"),
            ft.dropdown.Option("B"),
        ],
    )
    # Testing late assignment
    dd.on_change = on_change

    t = ft.Text()

    page.add(dd, t)

ft.app(target=main)
