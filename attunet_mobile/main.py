import os
from pathlib import Path

import flet as ft

from config import APP_TITLE, UPLOAD_DIR, WEB_UPLOAD_SECRET
from services.analysis_service import AnalysisService
from state.app_state import AppState
from views.sampling_view import SamplingView
from views.settings_view import SettingsView


def main(page: ft.Page):
    page.title = APP_TITLE
    page.window_width = 360
    page.window_height = 780
    page.window_resizable = False
    page.padding = 0
    page.spacing = 0
    page.bgcolor = "#0F141B"
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = ft.ScrollMode.AUTO

    app_state = AppState.load()
    analysis_service = AnalysisService()
    content = ft.Container(expand=True)
    selected_index = {"value": 0}
    sampling_view = SamplingView(page, app_state, analysis_service)
    settings_view = SettingsView(page, app_state)

    def build_appbar():
        titles = ["Amostragens", "Configuracoes"]
        return ft.AppBar(
            title=ft.Text(titles[selected_index["value"]], color="white", weight=ft.FontWeight.W_700),
            bgcolor="#0B6E1B",
            center_title=False,
        )

    def refresh_view():
        page.appbar = build_appbar()
        if selected_index["value"] == 0:
            content.content = sampling_view.build()
        else:
            page.floating_action_button = None
            content.content = settings_view.build()
        page.update()

    sampling_view.on_state_change = refresh_view

    def on_navigation_change(event):
        selected_index["value"] = int(event.data)
        refresh_view()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor="#1B222C",
        indicator_color="#334155",
        on_change=on_navigation_change,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.GRID_VIEW_OUTLINED,
                selected_icon=ft.Icons.GRID_VIEW_ROUNDED,
                label="Amostragens",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS_ROUNDED,
                label="Configuracoes",
            ),
        ],
    )

    page.add(content)
    refresh_view()


if __name__ == "__main__":
    os.environ.setdefault("FLET_SECRET_KEY", WEB_UPLOAD_SECRET)
    ft.run(
        main,
        assets_dir=str(Path(__file__).parent / "assets"),
        upload_dir=str(UPLOAD_DIR),
    )
