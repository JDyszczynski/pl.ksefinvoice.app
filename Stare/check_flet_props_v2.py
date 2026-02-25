import flet as ft
import inspect
import sys

try:
    print("PopupMenuItem args:", inspect.signature(ft.PopupMenuItem.__init__))
except Exception as e:
    print("Error:", e)
