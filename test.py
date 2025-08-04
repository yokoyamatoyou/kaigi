import flet as ft


def main(page: ft.Page):
    try:
        c = ft.Colors.PRIMARY
        t = ft.Text(f"Primary color is: {c}", color=ft.Colors.GREEN)
        page.add(t)
        page.update()
        print("ft.Colors seems to be working.")
    except AttributeError as e:
        print(f"Error accessing ft.Colors: {e}")


if __name__ == "__main__":
    ft.app(target=main)