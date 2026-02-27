import flet as ft

def create_welcome_view(on_start_click):
    return ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            [
                ft.Text("Witaj w KSeF Invoice", size=40, color=ft.Colors.BLACK),
                ft.ElevatedButton("Start", on_click=on_start_click)
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )
