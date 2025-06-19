import flet as ft

def main(page: ft.Page):
    try:
        c = ft.colors.PRIMARY
        t = ft.Text(f"Primary color is: {c}", color=ft.colors.GREEN)
        page.add(t)
        page.update()
        print("ft.colors seems to be working.")
    except AttributeError as e:
        print(f"Error accessing ft.colors: {e}")

if __name__ == "__main__":
    ft.app(target=main)