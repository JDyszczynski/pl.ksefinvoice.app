import flet as ft
from datetime import datetime

def main(page: ft.Page):
    page.title = "Test Dialog"
    
    def open_dlg(e):
        dlg = ft.AlertDialog(
            title=ft.Text("Hello World"),
            content=ft.Text("This is a dialog"),
            actions=[
                ft.TextButton("Close", on_click=lambda e: close_dlg(dlg))
            ],
        )
        page.dialog = dlg
        dlg.open = True
        page.update()
        print("Dialog opened (method 1)")

    def close_dlg(dlg):
        dlg.open = False
        page.update()

    btn = ft.ElevatedButton("Open Dialog (page.dialog)", on_click=open_dlg)
    page.add(btn)

ft.app(target=main)