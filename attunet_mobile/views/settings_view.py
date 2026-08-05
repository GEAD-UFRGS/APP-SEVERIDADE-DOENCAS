import flet as ft


class SettingsView:
    def __init__(self, page: ft.Page, app_state):
        self.page = page
        self.app_state = app_state
        self.confidence_text = ft.Text(
            f"Confianca atual: {self.app_state.settings.confidence:.2f}",
            color="#E5E7EB",
        )
        self.sensitivity_text = ft.Text(
            f"Sensibilidade atual: {self.app_state.settings.sensitivity:.2f}",
            color="#E5E7EB",
        )
        self.status_text = ft.Text("", color="#C9D1D9")
        self.hybrid_threshold_checkbox = ft.Checkbox(
            value=self.app_state.settings.use_hybrid_threshold,
            label="Utilizar limiar hibrido",
            check_color="white",
            active_color="#4ADE80",
            label_style=ft.TextStyle(color="white"),
        )
        self.confidence_slider = ft.Slider(
            min=0.05,
            max=0.95,
            divisions=18,
            value=self.app_state.settings.confidence,
            label="{value}",
            on_change=self._on_confidence_change,
        )
        self.sensitivity_slider = ft.Slider(
            min=0.0,
            max=1.0,
            divisions=20,
            value=self.app_state.settings.sensitivity,
            label="{value}",
            on_change=self._on_sensitivity_change,
        )

    def build(self):
        return ft.Container(
            expand=True,
            width=390,
            padding=ft.Padding(left=18, top=18, right=18, bottom=24),
            alignment=ft.Alignment.TOP_CENTER,
            content=ft.Column(
                controls=[
                    ft.Text("Configuracoes", size=24, weight=ft.FontWeight.W_700, color="white"),
                    ft.Text(
                        "Ajuste o limiar usado para transformar a saida do modelo em mascara.",
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
                                ft.Text("Confianca do modelo", size=20, weight=ft.FontWeight.W_700, color="white"),
                                self.confidence_slider,
                                self.confidence_text,
                                ft.Text("Sensibilidade da classificacao", size=20, weight=ft.FontWeight.W_700, color="white"),
                                self.sensitivity_slider,
                                self.sensitivity_text,
                                self.hybrid_threshold_checkbox,
                                ft.Text(
                                    "Ligado: mistura o limiar absoluto 53.5 com ajuste adaptivo e sensibilidade. Desligado: usa o modo atual por imagem.",
                                    size=13,
                                    color="#AAB2BF",
                                ),
                                ft.FilledButton("Salvar configuracao", icon=ft.Icons.SAVE_ROUNDED, on_click=self._save),
                                self.status_text,
                            ],
                        ),
                    ),
                ],
                spacing=16,
            ),
        )

    def _on_confidence_change(self, event: ft.ControlEvent):
        self.confidence_text.value = f"Confianca atual: {event.control.value:.2f}"
        self.page.update()

    def _on_sensitivity_change(self, event: ft.ControlEvent):
        self.sensitivity_text.value = f"Sensibilidade atual: {event.control.value:.2f}"
        self.page.update()

    def _save(self, _):
        self.app_state.settings.confidence = float(self.confidence_slider.value)
        self.app_state.settings.sensitivity = float(self.sensitivity_slider.value)
        self.app_state.settings.use_hybrid_threshold = bool(self.hybrid_threshold_checkbox.value)
        self.app_state.save_settings()
        self.status_text.value = "Configuracao salva em json."
        self.page.update()
