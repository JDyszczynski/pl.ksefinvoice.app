import flet as ft

def main(page: ft.Page):
    btn = ft.ElevatedButton("Test Button")
    page.add(btn)
    
    try:
        print(f"Button content: {btn.content}")
        if btn.content:
             print(f"Content value: {btn.content.value}")
    except AttributeError:
        print("Button has no attribute 'content'")
        
    try:
        btn.text = "New Text"
        print(f"Button text after set: {btn.text}")
    except AttributeError:
        print("Button has no attribute 'text' for setting")

    page.update()

ft.app(target=main)
