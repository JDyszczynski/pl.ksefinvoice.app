import flet as ft

def main(page: ft.Page):
    print("\n--- ft.SegmentedButton ---")
    try:
        sb = ft.SegmentedButton(
            segments=[
                ft.Segment(value="0", label=ft.Text("Basic"), icon=ft.Icon(ft.icons.DESCRIPTION)),
            ],
            selected={"0"},
            on_change=lambda e: print(e.data)
        )
        print("ft.SegmentedButton initialized OK")
        print("Dir:", dir(sb))
    except Exception as e:
        print(f"ft.SegmentedButton failed: {e}")
        # Try checking if ft.icons works or need string
        try:
             sb = ft.SegmentedButton(
                segments=[
                    ft.Segment(value="0", label=ft.Text("Basic"), icon=ft.Icon("description")),
                ],
                selected={"0"}
            )
             print("ft.SegmentedButton (with string icon) initialized OK")
        except Exception as ex:
             print(f"ft.SegmentedButton (string icon) failed: {ex}")

ft.app(target=main)
