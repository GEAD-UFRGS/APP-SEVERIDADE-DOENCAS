import flet as ft

from config import DEFAULT_SETTINGS

MAX_CONTENT_WIDTH = 430
COMPACT_BREAKPOINT = 360


class SettingsView:
    def __init__(self, page: ft.Page, app_state):
        self.page = page
        self.app_state = app_state
        self.confidence_text = ft.Text(
            f"Confiança atual: {self.app_state.settings.confidence:.2f}",
            color="#E5E7EB",
        )
        self.status_text = ft.Text("", color="#C9D1D9")
        self.confidence_slider = ft.Slider(
            min=0.05,
            max=0.95,
            divisions=18,
            value=self.app_state.settings.confidence,
            label="{value}",
            on_change=self._on_confidence_change,
        )

    def build(self):
        content_width = self._content_width()
        content_padding = self._content_padding(content_width)
        return ft.Container(
            expand=True,
            width=content_width,
            padding=ft.Padding(left=content_padding, top=18, right=content_padding, bottom=24),
            alignment=ft.Alignment.TOP_CENTER,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Text("Configurações", size=24, weight=ft.FontWeight.W_700, color="white"),
                    ft.Text(
                        "Ajuste apenas a segmentação da folha. O tipo de dano é escolhido ao criar cada leitura.",
                        size=15,
                        color="#AAB2BF",
                    ),
                    ft.Container(
                        bgcolor="#1F2937",
                        border_radius=22,
                        padding=18,
                        content=ft.Column(
                            spacing=14,
                            controls=[
                                ft.Text("Segmentação da folha", size=20, weight=ft.FontWeight.W_700, color="white"),
                                ft.Text(
                                    "Define a confiança mínima do modelo ONNX para separar a folha do fundo. Valores maiores deixam o recorte mais rigoroso.",
                                    size=13,
                                    color="#AAB2BF",
                                ),
                                self.confidence_slider,
                                self.confidence_text,
                                ft.FilledButton("Salvar configuração", icon=ft.Icons.SAVE_ROUNDED, on_click=self._save),
                                ft.OutlinedButton("Restaurar padrão", icon=ft.Icons.RESTART_ALT_ROUNDED, on_click=self._restore_defaults),
                                self.status_text,
                            ],
                        ),
                    ),
                ],
                spacing=16,
            ),
        )

    def _content_width(self):
        page_width = self.page.width or MAX_CONTENT_WIDTH
        return min(MAX_CONTENT_WIDTH, max(0, page_width))

    def _content_padding(self, content_width):
        return 14 if content_width < COMPACT_BREAKPOINT else 18

    def _on_confidence_change(self, event: ft.ControlEvent):
        self.confidence_text.value = f"Confiança atual: {event.control.value:.2f}"
        self.page.update()

    def _save(self, _):
        self.app_state.settings.confidence = float(self.confidence_slider.value)
        self.app_state.save_settings()
        self.status_text.value = "Configuração salva em JSON."
        self.page.update()

    def _restore_defaults(self, _):
        self.confidence_slider.value = float(DEFAULT_SETTINGS["confidence"])
        self.confidence_text.value = f"Confiança atual: {self.confidence_slider.value:.2f}"
        self.app_state.settings.confidence = self.confidence_slider.value
        self.app_state.save_settings()
        self.status_text.value = "Configuração padrão restaurada."
        self.page.update()
