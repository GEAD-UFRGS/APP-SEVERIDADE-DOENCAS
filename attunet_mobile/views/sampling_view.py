import asyncio
import base64
import uuid
from datetime import date, datetime
from pathlib import Path

import flet as ft

try:
    import flet_camera as ft_camera
except ImportError:
    ft_camera = None

try:
    import flet_permission_handler as fph
except ImportError:
    fph = None

from config import DAMAGE_MODE_LABELS, WEB_IMAGE_BATCH_LIMIT, WEB_IMAGE_COMPRESSION_QUALITY
from services.image_service import (
    list_test_images_from_folder,
    pick_desktop_directory_path,
    pick_desktop_image_paths,
    prepare_selected_images,
    save_temp_image_bytes,
)
from state.app_state import ParcelImage

MAX_CONTENT_WIDTH = 430
COMPACT_BREAKPOINT = 360
CARD_PADDING = 16
DEFAULT_VIEWER_SIZE = 322
MIN_VIEWER_SIZE = 180
GREEN = "#0B6E1B"
SURFACE = "#1F2937"
SURFACE_DARK = "#111827"
TEXT = "#F1F5F9"
MUTED = "#AAB2BF"


class SamplingView:
    def __init__(self, page: ft.Page, app_state, analysis_service, on_state_change=None):
        self.page = page
        self.app_state = app_state
        self.analysis_service = analysis_service
        self.on_state_change = on_state_change
        self.file_picker = ft.FilePicker()
        self.page.services.append(self.file_picker)
        self.permission_handler = None
        if fph is not None and self._permission_handler_supported():
            self.permission_handler = fph.PermissionHandler()
            self.page.services.append(self.permission_handler)
        self.camera = None
        self.camera_status_text = None
        self.viewer_token = None
        self.viewer_session_key = uuid.uuid4().hex
        self.feedback_text = ft.Text("", color="#94A3B8", size=13, text_align=ft.TextAlign.CENTER)
        self.progress_bar = ft.ProgressBar(value=0, color="#22C55E", bgcolor="#334155", visible=False)
        self.process_button = ft.FilledButton(
            "Processar teste",
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            on_click=self._start_process_unit_test,
            height=54,
        )
        self.experiment_process_button = ft.FilledButton(
            "Processar experimento",
            icon=ft.Icons.PLAY_ARROW_ROUNDED,
            on_click=self._start_process_experiment,
            height=56,
        )
        self.view_mode_dropdown = ft.Dropdown(
            value="original",
            label="Modo de visualização",
            options=[
                ft.dropdown.Option("original", "Original"),
                ft.dropdown.Option("sobreposicao", "Sobreposição"),
                ft.dropdown.Option("mapa", "Mapa"),
            ],
            on_select=self._change_view_mode,
            filled=True,
            fill_color=SURFACE_DARK,
            border_color="#334155",
            color="white",
        )
        self.current_healthy_text = self._metric_value("--", "#86EFAC")
        self.current_severity_text = self._metric_value("--", "#FDBA74")
        self.avg_healthy_text = ft.Text("--", color="#D1FAE5", size=14, weight=ft.FontWeight.W_600)
        self.avg_severity_text = ft.Text("--", color="#FFEDD5", size=14, weight=ft.FontWeight.W_600)
        self.segmented_image = ft.Image(src="", fit="contain", border_radius=16, visible=False)
        self.placeholder = ft.Container(
            border_radius=16,
            bgcolor=SURFACE,
            alignment=ft.Alignment.CENTER,
            padding=20,
            content=ft.Text("Adicione imagens para visualizar.", color="#9AA4B2", size=15, text_align=ft.TextAlign.CENTER),
        )
        self.viewer_stack = ft.Stack(fit=ft.StackFit.EXPAND, controls=[self.placeholder, self.segmented_image])

    def build(self):
        self._apply_responsive_sizes()
        level = self.app_state.active_level
        if level == "experiment" and self.app_state.get_active_experiment():
            return self._build_experiment()
        if level == "treatment" and self.app_state.get_active_treatment():
            return self._build_treatment()
        if level == "plot" and self.app_state.get_active_plot():
            return self._build_plot()
        if level in {"reading", "test"} and self.app_state.get_active_parcel():
            return self._build_reading()
        self.app_state.active_level = "home"
        return self._build_home()

    def current_title(self):
        titles = {
            "home": "SevSearch",
            "experiment": "Experimento",
            "treatment": "Tratamento",
            "plot": "Parcela",
            "reading": "Leitura",
            "test": "Teste unitário",
        }
        return titles.get(self.app_state.active_level, "SevSearch")

    def _build_home(self):
        experiments = [self._experiment_card(item) for item in self.app_state.experiments]
        if not experiments:
            experiments = [self._empty_card("Nenhum experimento criado. Comece pelo botão acima.")]
        return self._screen(
            [
                ft.Text("Amostragens", size=28, weight=ft.FontWeight.W_700, color=TEXT),
                ft.Text("Organize avaliações de campo e acompanhe resultados por tratamento.", size=15, color=MUTED),
                self._primary_action(
                    ft.Icons.ADD_ROUNDED,
                    "Criar novo experimento",
                    "Defina nome, data, cultura e descrição.",
                    self._open_add_experiment_dialog,
                ),
                self._primary_action(
                    ft.Icons.SCIENCE_ROUNDED,
                    "Novo teste unitário",
                    "Valide o modelo rapidamente sem salvar dados.",
                    self._start_unit_test,
                ),
                ft.Text("Experimentos em andamento", size=20, weight=ft.FontWeight.W_700, color=TEXT),
                *experiments,
            ]
        )

    def _build_experiment(self):
        experiment = self.app_state.get_active_experiment()
        treatments = [self._treatment_card(treatment) for treatment in experiment.treatments]
        if not treatments:
            treatments = [self._empty_card("Nenhum tratamento neste experimento.")]
        self.experiment_process_button.disabled = not self._experiment_ready_readings(experiment)
        return self._screen(
            [
                self._header(experiment.name, f"{experiment.culture} • início {experiment.start_date}"),
                ft.Text(experiment.description or "Sem descrição adicional.", size=14, color=MUTED),
                self._primary_action(
                    ft.Icons.ADD_ROUNDED,
                    "Adicionar tratamento",
                    "Crie um novo tratamento dentro do experimento.",
                    self._open_add_treatment_dialog,
                ),
                self.experiment_process_button,
                self.progress_bar,
                self._feedback_line(),
                ft.Text("Tratamentos", size=20, weight=ft.FontWeight.W_700, color=TEXT),
                *treatments,
            ]
        )

    def _build_treatment(self):
        treatment = self.app_state.get_active_treatment()
        parcels = [self._plot_card(plot) for plot in treatment.parcels]
        if not parcels:
            parcels = [self._empty_card("Nenhuma parcela neste tratamento.")]
        return self._screen(
            [
                self._header(treatment.name, treatment.description or "Tratamento do experimento"),
                self._treatment_result_card(treatment),
                self._primary_action(
                    ft.Icons.ADD_ROUNDED,
                    "Adicionar parcela",
                    "Crie uma parcela para receber leituras.",
                    self._open_add_plot_dialog,
                ),
                ft.Text("Parcelas", size=20, weight=ft.FontWeight.W_700, color=TEXT),
                *parcels,
            ]
        )

    def _build_plot(self):
        plot = self.app_state.get_active_plot()
        readings = [self._reading_card(reading) for reading in plot.readings]
        if not readings:
            readings = [self._empty_card("Nenhuma leitura registrada nesta parcela.")]
        return self._screen(
            [
                self._header(plot.name, plot.description or "Parcela do tratamento"),
                self._summary_metrics(plot.average_healthy_pct(), plot.average_severity_pct(), len(plot.processed_results())),
                self._primary_action(
                    ft.Icons.ADD_ROUNDED,
                    "Adicionar leitura",
                    "Defina a data e a quantidade de imagens desta leitura.",
                    self._open_add_reading_dialog,
                ),
                ft.Text("Leituras", size=20, weight=ft.FontWeight.W_700, color=TEXT),
                *readings,
            ]
        )

    def _build_reading(self):
        reading = self.app_state.get_active_parcel()
        self._refresh_reading(reading)
        is_test = reading.validation_mode
        action_controls = []
        if not reading.processed or is_test:
            action_controls.append(
                self._primary_action(
                    ft.Icons.PHOTO_LIBRARY_ROUNDED,
                    "Adicionar imagens",
                    "Selecione as imagens da galeria.",
                    self._start_pick_images,
                )
            )
            if self._camera_capture_supported():
                action_controls.append(
                    self._primary_action(
                        ft.Icons.PHOTO_CAMERA_ROUNDED,
                        "Fotografar",
                        "Adicione uma imagem usando a câmera traseira.",
                        self._start_capture_image,
                    )
                )
            if self._is_native_desktop():
                action_controls.append(
                    self._primary_action(
                        ft.Icons.FOLDER_OPEN_ROUNDED,
                        "Carregar pasta de teste",
                        "Selecione uma pasta local com imagens.",
                        self._start_load_test_images,
                    )
                )
        controls = [
            self._header(reading.name, self._reading_subtitle(reading)),
            ft.Text(reading.description or ("Dados temporários; nada será salvo." if is_test else "Sem descrição adicional."), size=14, color=MUTED),
            *action_controls,
            self._feedback_line(),
        ]
        if is_test:
            controls.extend([self.process_button, self.progress_bar])
        controls.extend([self._viewer_card(), self._image_actions(reading), self._metrics_card(), self._view_mode_card()])
        if not is_test:
            controls.append(
                ft.Text(
                    "O processamento desta leitura é iniciado pelo botão Processar experimento.",
                    color=MUTED,
                    size=13,
                    text_align=ft.TextAlign.CENTER,
                )
            )
        return self._screen(controls)

    def _screen(self, controls):
        width = self._content_width()
        padding = self._content_padding(width)
        return ft.Container(
            expand=True,
            width=width,
            padding=ft.Padding(left=padding, top=18, right=padding, bottom=24),
            alignment=ft.Alignment.TOP_CENTER,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=16,
                controls=controls,
            ),
        )

    def _header(self, title, subtitle):
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, icon_color="white", on_click=self._navigate_back),
                ft.Column(
                    expand=True,
                    spacing=3,
                    controls=[
                        ft.Text(title, size=23, weight=ft.FontWeight.W_700, color=TEXT),
                        ft.Text(subtitle, size=13, color=MUTED),
                    ],
                ),
            ],
        )

    def _primary_action(self, icon, title, subtitle, on_click):
        return ft.Container(
            bgcolor=SURFACE,
            border_radius=20,
            padding=16,
            on_click=on_click,
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=56,
                        height=56,
                        border_radius=16,
                        bgcolor=GREEN,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon, color="white", size=28),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            ft.Text(title, color=TEXT, size=18, weight=ft.FontWeight.W_700),
                            ft.Text(subtitle, color=MUTED, size=13),
                        ],
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color="#CBD5E1"),
                ],
            ),
        )

    def _list_card(self, icon, title, subtitle, details, on_click, badge=None, on_delete=None):
        detail_controls = [ft.Text(subtitle, color=MUTED, size=13)]
        if details:
            detail_controls.append(ft.Text(details, color="#CBD5E1", size=12))
        if badge:
            detail_controls.append(self._badge(badge[0], badge[1]))
        trailing_controls = []
        if on_delete:
            trailing_controls.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    icon_color="#FCA5A5",
                    icon_size=21,
                    tooltip="Excluir",
                    on_click=on_delete,
                )
            )
        trailing_controls.append(ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color="#CBD5E1"))
        return ft.Container(
            bgcolor=SURFACE,
            border_radius=20,
            padding=16,
            on_click=on_click,
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=54,
                        height=54,
                        border_radius=15,
                        bgcolor=GREEN,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon, color="white", size=27),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[ft.Text(title, color=TEXT, size=18, weight=ft.FontWeight.W_700), *detail_controls],
                    ),
                    *trailing_controls,
                ],
            ),
        )

    def _experiment_card(self, experiment):
        treatments, parcels, readings = experiment.counts()
        status = "Em andamento"
        return self._list_card(
            ft.Icons.SCIENCE_ROUNDED,
            experiment.name,
            f"{experiment.culture} • {experiment.start_date}",
            f"{treatments} tratamentos • {parcels} parcelas • {readings} leituras",
            lambda _, item_id=experiment.id: self._open_experiment(item_id),
            (status, "#166534"),
            lambda _, item=experiment: self._confirm_delete_experiment(item),
        )

    def _treatment_card(self, treatment):
        readings = [reading for plot in treatment.parcels for reading in plot.readings]
        processed = sum(reading.processed for reading in readings)
        details = f"{processed} leituras processadas"
        if treatment.processed_results():
            details += f" • Sadia {treatment.average_healthy_pct():.2f}% • Severidade {treatment.average_severity_pct():.2f}%"
        return self._list_card(
            ft.Icons.INVENTORY_2_ROUNDED,
            treatment.name,
            f"{len(treatment.parcels)} parcelas • {len(readings)} leituras",
            details,
            lambda _, item_id=treatment.id: self._open_treatment(item_id),
            on_delete=lambda _, item=treatment: self._confirm_delete_treatment(item),
        )

    def _plot_card(self, plot):
        processed = sum(reading.processed for reading in plot.readings)
        details = f"{processed}/{len(plot.readings)} leituras processadas"
        return self._list_card(
            ft.Icons.GRID_VIEW_ROUNDED,
            plot.name,
            f"{len(plot.readings)} leituras",
            details,
            lambda _, item_id=plot.id: self._open_plot(item_id),
            on_delete=lambda _, item=plot: self._confirm_delete_plot(item),
        )

    def _reading_card(self, reading):
        if reading.processed:
            details = f"Sadia {reading.average_healthy_pct():.2f}% • Severidade {reading.average_severity_pct():.2f}%"
            badge = ("Processada", "#166534")
        elif reading.is_ready_to_process():
            details = f"{len(reading.images)}/{reading.target_images} imagens"
            badge = ("Pronta", "#1D4ED8")
        else:
            details = f"{len(reading.images)}/{reading.target_images} imagens"
            badge = ("Pendente", "#92400E")
        return self._list_card(
            ft.Icons.CALENDAR_MONTH_ROUNDED,
            f"Leitura • {reading.date}",
            reading.damage_mode_label,
            details,
            lambda _, item_id=reading.id: self._open_reading(item_id),
            badge,
            lambda _, item=reading: self._confirm_delete_reading(item),
        )

    def _badge(self, text, color):
        return ft.Container(
            bgcolor=color,
            border_radius=10,
            padding=ft.Padding(left=9, top=4, right=9, bottom=4),
            content=ft.Text(text, color="white", size=11, weight=ft.FontWeight.W_600),
        )

    def _empty_card(self, text):
        return ft.Container(
            bgcolor=SURFACE,
            border_radius=20,
            padding=22,
            content=ft.Text(text, color="#CBD5E1", text_align=ft.TextAlign.CENTER),
        )

    def _treatment_result_card(self, treatment):
        return ft.Container(
            bgcolor=SURFACE_DARK,
            border_radius=20,
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text("Resultado do tratamento", color=TEXT, size=18, weight=ft.FontWeight.W_700),
                    self._summary_metrics(
                        treatment.average_healthy_pct(),
                        treatment.average_severity_pct(),
                        len(treatment.processed_results()),
                    ),
                ],
            ),
        )

    def _summary_metrics(self, healthy, severity, image_count):
        return ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    spacing=10,
                    controls=[
                        self._summary_box("Área sadia", healthy, "#0F2A1C", "#86EFAC"),
                        self._summary_box("Severidade", severity, "#2D190F", "#FDBA74"),
                    ],
                ),
                ft.Text(f"Média ponderada por {image_count} imagens processadas", color=MUTED, size=12),
            ],
        )

    def _summary_box(self, title, value, bgcolor, color):
        return ft.Container(
            expand=True,
            bgcolor=bgcolor,
            border_radius=16,
            padding=14,
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Text(title, color="#CBD5E1", size=12),
                    ft.Text(f"{value:.2f}%", color=color, size=24, weight=ft.FontWeight.W_700),
                ],
            ),
        )

    def _refresh_reading(self, reading):
        current = reading.current_image()
        count = len(reading.images)
        remaining = reading.remaining_images()
        self.feedback_text.color = "#94A3B8"
        self.process_button.disabled = not reading.is_ready_to_process()
        if reading.processed and not reading.images:
            self.feedback_text.value = "Resultados recuperados. As imagens não são salvas após fechar o aplicativo."
        elif reading.validation_mode:
            self.feedback_text.value = self._loaded_images_label(count, reading)
        elif remaining:
            self.feedback_text.value = f"Faltam {remaining} {'imagem' if remaining == 1 else 'imagens'} para completar a leitura."
        else:
            self.feedback_text.value = "Leitura completa e pronta para o processamento do experimento."
        self.avg_healthy_text.value = f"{reading.average_healthy_pct():.2f}%" if reading.all_results() else "--"
        self.avg_severity_text.value = f"{reading.average_severity_pct():.2f}%" if reading.all_results() else "--"
        if current is None:
            self.segmented_image.src = ""
            self.segmented_image.visible = False
            self.placeholder.visible = True
            self.placeholder.content.value = "As imagens desta leitura não estão disponíveis." if reading.processed else "Adicione imagens para visualizar."
            self.view_mode_dropdown.disabled = True
            self.current_healthy_text.value = "--"
            self.current_severity_text.value = "--"
            self._sync_viewer_session(None)
            return
        self.view_mode_dropdown.disabled = False
        self.view_mode_dropdown.value = current.view_mode
        self._sync_viewer_session(current)
        source = current.view_sources.get(current.view_mode) if current.processed else self._original_image_source(current)
        if source:
            self.segmented_image.src = source
            self.segmented_image.visible = True
            self.placeholder.visible = False
        else:
            self.segmented_image.visible = False
            self.placeholder.visible = True
            self.placeholder.content.value = "Não foi possível exibir esta imagem."
        self.current_healthy_text.value = f"{current.healthy_pct:.2f}%" if current.processed else "--"
        self.current_severity_text.value = f"{current.severity_pct:.2f}%" if current.processed else "--"

    def _viewer_card(self):
        reading = self.app_state.get_active_parcel()
        image_count = len(reading.images) if reading else 0
        viewer_size = self._viewer_size()
        interactive_viewer = ft.InteractiveViewer(
            key=self.viewer_session_key,
            content=ft.Container(width=viewer_size, height=viewer_size, alignment=ft.Alignment.CENTER, content=self.viewer_stack),
            min_scale=1.0,
            max_scale=5.0,
            boundary_margin=96,
            interaction_update_interval=16,
            scale_factor=120,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        return ft.Container(
            bgcolor=SURFACE_DARK,
            border_radius=20,
            padding=16,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Stack(
                width=viewer_size,
                height=viewer_size,
                fit=ft.StackFit.EXPAND,
                controls=[
                    interactive_viewer,
                    ft.Container(
                        left=8,
                        top=max(0, (viewer_size - 50) / 2),
                        visible=image_count > 1,
                        content=self._viewer_nav_zone(ft.Icons.CHEVRON_LEFT_ROUNDED, self._previous_image),
                    ),
                    ft.Container(
                        right=8,
                        top=max(0, (viewer_size - 50) / 2),
                        visible=image_count > 1,
                        content=self._viewer_nav_zone(ft.Icons.CHEVRON_RIGHT_ROUNDED, self._next_image),
                    ),
                ],
            ),
        )

    def _viewer_nav_zone(self, icon, on_click):
        return ft.Container(
            width=38,
            height=50,
            alignment=ft.Alignment.CENTER,
            on_click=on_click,
            content=ft.Container(
                width=34,
                height=34,
                border_radius=17,
                bgcolor="#0F172ACC",
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(icon, color="#E5E7EB", size=20),
            ),
        )

    def _image_actions(self, reading):
        current = reading.current_image()
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(
                    f"Imagem {reading.current_index + 1} de {len(reading.images)}" if reading.images else "Nenhuma imagem",
                    color=MUTED,
                    size=13,
                ),
                ft.TextButton(
                    "Excluir imagem",
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    on_click=self._delete_current_image,
                    disabled=current is None,
                ),
            ],
        )

    def _metrics_card(self):
        return ft.Container(
            bgcolor=SURFACE,
            border_radius=20,
            padding=16,
            content=ft.Row(
                spacing=12,
                controls=[
                    self._metric_box("Área sadia", self.current_healthy_text, self.avg_healthy_text, "#0F2A1C"),
                    self._metric_box("Severidade", self.current_severity_text, self.avg_severity_text, "#2D190F"),
                ],
            ),
        )

    def _metric_box(self, title, current, average, bgcolor):
        return ft.Container(
            expand=True,
            bgcolor=bgcolor,
            border_radius=16,
            padding=13,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5,
                controls=[ft.Text(title, color="#CBD5E1", size=12), current, ft.Text("Média", color=MUTED, size=11), average],
            ),
        )

    def _view_mode_card(self):
        return ft.Container(
            bgcolor=SURFACE,
            border_radius=20,
            padding=16,
            content=ft.Column(
                spacing=10,
                controls=[ft.Text("Visualização", color=TEXT, size=17, weight=ft.FontWeight.W_700), self.view_mode_dropdown],
            ),
        )

    def _feedback_line(self):
        return ft.Container(padding=ft.Padding(left=8, top=0, right=8, bottom=0), content=self.feedback_text)

    def _metric_value(self, value, color):
        return ft.Text(value, color=color, size=27, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER)

    def _open_add_experiment_dialog(self, _):
        fields = {
            "name": ft.TextField(label="Nome do experimento", autofocus=True),
            "date": ft.TextField(label="Data de início", value=date.today().strftime("%d/%m/%Y")),
            "culture": ft.TextField(label="Cultura", value="Trigo"),
            "description": ft.TextField(label="Descrição (opcional)", multiline=True, min_lines=2, max_lines=3),
        }

        def create(feedback):
            name = (fields["name"].value or "").strip()
            culture = (fields["culture"].value or "").strip()
            formatted_date = self._normalize_date(fields["date"].value)
            if not name or not culture:
                feedback.value = "Informe o nome e a cultura."
                return False
            if formatted_date is None:
                feedback.value = "Informe a data no formato DD/MM/AAAA."
                return False
            experiment = self.app_state.add_experiment(name, formatted_date, culture, (fields["description"].value or "").strip())
            self.app_state.open_experiment(experiment.id)
            return True

        self._show_form_dialog("Novo experimento", list(fields.values()), create)

    def _open_add_treatment_dialog(self, _):
        name = ft.TextField(label="Nome do tratamento", autofocus=True)
        description = ft.TextField(label="Descrição (opcional)", multiline=True, min_lines=2, max_lines=3)

        def create(feedback):
            if not (name.value or "").strip():
                feedback.value = "Informe o nome do tratamento."
                return False
            self.app_state.add_treatment(name.value.strip(), (description.value or "").strip())
            return True

        self._show_form_dialog("Novo tratamento", [name, description], create)

    def _open_add_plot_dialog(self, _):
        name = ft.TextField(label="Nome da parcela", autofocus=True)
        description = ft.TextField(label="Descrição (opcional)", multiline=True, min_lines=2, max_lines=3)

        def create(feedback):
            if not (name.value or "").strip():
                feedback.value = "Informe o nome da parcela."
                return False
            self.app_state.add_plot(name.value.strip(), (description.value or "").strip())
            return True

        self._show_form_dialog("Nova parcela", [name, description], create)

    def _open_add_reading_dialog(self, _):
        reading_date = ft.TextField(label="Data da leitura", value=date.today().strftime("%d/%m/%Y"), autofocus=True)
        target = ft.TextField(label="Quantidade de imagens", value="3", keyboard_type=ft.KeyboardType.NUMBER)
        damage_mode = self._damage_mode_dropdown()
        description = ft.TextField(label="Descrição (opcional)", multiline=True, min_lines=2, max_lines=3)

        def create(feedback):
            formatted_date = self._normalize_date(reading_date.value)
            try:
                target_images = int(target.value)
            except (TypeError, ValueError):
                target_images = 0
            if formatted_date is None:
                feedback.value = "Informe a data no formato DD/MM/AAAA."
                return False
            if target_images <= 0:
                feedback.value = "A quantidade de imagens deve ser maior que zero."
                return False
            if not damage_mode.value:
                feedback.value = "Selecione o tipo de dano que será analisado."
                return False
            reading = self.app_state.add_reading(
                formatted_date,
                target_images,
                (description.value or "").strip(),
                damage_mode.value,
            )
            self.app_state.open_reading(reading.id)
            return True

        self._show_form_dialog("Nova leitura", [reading_date, target, damage_mode, description], create)

    def _damage_mode_dropdown(self):
        return ft.Dropdown(
            label="Tipo de dano",
            hint_text="Selecione uma opção",
            options=[ft.dropdown.Option(value, label) for value, label in DAMAGE_MODE_LABELS.items()],
            filled=True,
            fill_color=SURFACE_DARK,
            border_color="#475569",
            color="white",
        )

    def _show_form_dialog(self, title, fields, create):
        feedback = ft.Text("", color="#FCA5A5")

        def close(_=None):
            self.page.pop_dialog()
            self.page.update()

        def submit(_):
            if create(feedback):
                close()
                self._request_refresh()
            else:
                self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE,
            title=ft.Text(title, color="white"),
            content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=[*fields, feedback]),
            actions=[ft.TextButton("Cancelar", on_click=close), ft.FilledButton("Criar", on_click=submit)],
        )
        self.page.show_dialog(dialog)

    def _confirm_delete_experiment(self, experiment):
        self._show_delete_dialog(
            item_type="experimento",
            item_name=experiment.name,
            nested_items="tratamentos, parcelas, leituras e resultados",
            delete_action=lambda: self.app_state.delete_experiment(experiment.id),
        )

    def _confirm_delete_treatment(self, treatment):
        self._show_delete_dialog(
            item_type="tratamento",
            item_name=treatment.name,
            nested_items="parcelas, leituras e resultados",
            delete_action=lambda: self.app_state.delete_treatment(treatment.id),
        )

    def _confirm_delete_plot(self, plot):
        self._show_delete_dialog(
            item_type="parcela",
            item_name=plot.name,
            nested_items="leituras e resultados",
            delete_action=lambda: self.app_state.delete_plot(plot.id),
        )

    def _confirm_delete_reading(self, reading):
        self._show_delete_dialog(
            item_type="leitura",
            item_name=reading.date,
            nested_items="imagens temporárias e resultados",
            delete_action=lambda: self.app_state.delete_reading(reading.id),
        )

    def _show_delete_dialog(self, item_type, item_name, nested_items, delete_action):
        def close(_=None):
            self.page.pop_dialog()
            self.page.update()

        def confirm(_):
            delete_action()
            self.page.pop_dialog()
            self._request_refresh()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE,
            title=ft.Text(f"Excluir {item_type}?", color="white"),
            content=ft.Text(
                f'A exclusão de "{item_name}" também removerá {nested_items}. Esta ação não pode ser desfeita.',
                color="#CBD5E1",
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=close),
                ft.FilledButton(
                    "Excluir",
                    icon=ft.Icons.DELETE_ROUNDED,
                    bgcolor="#B91C1C",
                    color="white",
                    on_click=confirm,
                ),
            ],
        )
        self.page.show_dialog(dialog)

    async def _pick_images(self, _):
        reading = self.app_state.get_active_parcel()
        if reading is None or (reading.processed and not reading.validation_mode):
            return
        remaining = reading.remaining_images()
        if remaining == 0:
            self._set_feedback("A leitura já atingiu a quantidade definida.")
            return
        try:
            if self._is_native_desktop():
                selected = await asyncio.to_thread(pick_desktop_image_paths)
                if remaining is not None:
                    selected = selected[:remaining]
                paths = prepare_selected_images(selected, copy_local_files=False)
            else:
                files = await self.file_picker.pick_files(
                    allow_multiple=True,
                    file_type=ft.FilePickerFileType.IMAGE,
                    with_data=self.page.web,
                    compression_quality=WEB_IMAGE_COMPRESSION_QUALITY if self.page.web else 0,
                )
                if not files:
                    return
                limit = WEB_IMAGE_BATCH_LIMIT if remaining is None else min(remaining, WEB_IMAGE_BATCH_LIMIT) if self.page.web else remaining
                paths = prepare_selected_images(files[:limit], optimize_for_web=self.page.web, copy_local_files=True)
            self._append_images(reading, paths)
        except Exception as exc:
            self._set_feedback(f"Erro ao carregar imagens: {exc}", error=True)

    async def _load_test_images(self, _):
        reading = self.app_state.get_active_parcel()
        if reading is None or (reading.processed and not reading.validation_mode):
            return
        folder = await asyncio.to_thread(pick_desktop_directory_path)
        if folder is None:
            return
        paths, error = list_test_images_from_folder(folder)
        if error:
            self._set_feedback(error, error=True)
            return
        remaining = reading.remaining_images()
        self._append_images(reading, paths if remaining is None else paths[:remaining])

    def _append_images(self, reading, paths):
        if not paths:
            self._set_feedback("Nenhuma imagem válida foi carregada.", error=True)
            return
        for path in paths:
            reading.images.append(ParcelImage(uuid.uuid4().hex, path=str(path), view_mode="original"))
        reading.current_index = max(len(reading.images) - len(paths), 0)
        self.view_mode_dropdown.value = "original"
        self._set_feedback(self._loaded_images_label(len(reading.images), reading))
        self._request_refresh()

    async def _capture_image(self, _):
        reading = self.app_state.get_active_parcel()
        if reading is None or (reading.processed and not reading.validation_mode) or reading.remaining_images() == 0:
            return
        if ft_camera is None or self.permission_handler is None:
            self._set_feedback("A câmera não está disponível nesta versão.", error=True)
            return
        permission = await self.permission_handler.get_status(fph.Permission.CAMERA)
        if permission != fph.PermissionStatus.GRANTED:
            permission = await self.permission_handler.request(fph.Permission.CAMERA)
        if permission != fph.PermissionStatus.GRANTED:
            self._set_feedback("Permissão de câmera negada.", error=True)
            return
        await self._open_camera_dialog()

    async def _open_camera_dialog(self):
        self.camera_status_text = ft.Text("Inicializando câmera...", color="#CBD5E1", text_align=ft.TextAlign.CENTER)
        self.camera = ft_camera.Camera(expand=True, preview_enabled=True)

        def close(_=None):
            self.camera = None
            self.page.pop_dialog()
            self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=SURFACE_DARK,
            title=ft.Text("Fotografar", color="white"),
            content=ft.Container(
                width=min(320, max(240, (self.page.width or 390) - 48)),
                height=min(420, max(320, (self.page.height or 520) - 180)),
                content=ft.Column(
                    tight=True,
                    controls=[
                        ft.Container(expand=True, border_radius=16, clip_behavior=ft.ClipBehavior.HARD_EDGE, bgcolor="#020617", content=self.camera),
                        self.camera_status_text,
                    ],
                ),
            ),
            actions=[ft.TextButton("Cancelar", on_click=close), ft.FilledButton("Capturar", on_click=self._take_camera_picture)],
        )
        self.page.show_dialog(dialog)
        try:
            cameras = await self.camera.get_available_cameras()
            if not cameras:
                raise RuntimeError("Nenhuma câmera disponível.")
            selected = next((item for item in cameras if item.lens_direction == ft_camera.CameraLensDirection.BACK), cameras[0])
            await self.camera.initialize(description=selected, resolution_preset=ft_camera.ResolutionPreset.HIGH, enable_audio=False)
            self.camera_status_text.value = "Câmera pronta."
        except Exception as exc:
            self.camera_status_text.value = f"Erro ao iniciar câmera: {exc}"
        self.page.update()

    async def _take_camera_picture(self, _):
        reading = self.app_state.get_active_parcel()
        if reading is None or self.camera is None:
            return
        try:
            data = await self.camera.take_picture()
            path = save_temp_image_bytes(data, f"camera_{len(reading.images) + 1}.jpg", len(reading.images))
        except Exception as exc:
            self.camera_status_text.value = f"Erro ao capturar: {exc}"
            self.page.update()
            return
        self.camera = None
        self.page.pop_dialog()
        self._append_images(reading, [path])

    async def _process_unit_test(self, _):
        reading = self.app_state.get_active_parcel()
        if reading is None or not reading.validation_mode or not reading.is_ready_to_process():
            return
        await self._process_reading(reading, persist=False, label="teste")
        self._request_refresh()

    async def _process_experiment(self, _):
        experiment = self.app_state.get_active_experiment()
        if experiment is None:
            return
        pending_items = self._experiment_ready_readings(experiment)
        if not pending_items:
            self._set_feedback("Não há leituras completas aguardando processamento.")
            return
        total_images = sum(len(reading.images) for _, _, reading in pending_items)
        completed = 0
        self.progress_bar.visible = True
        self.progress_bar.value = 0
        self.experiment_process_button.disabled = True
        try:
            for treatment, plot, reading in pending_items:
                self.feedback_text.value = f"Processando {treatment.name} • {plot.name} • {reading.date}"
                self.page.update()
                for image in reading.images:
                    await self._process_image(image, reading.damage_mode)
                    completed += 1
                    self.progress_bar.value = completed / total_images
                    self.feedback_text.value = f"{completed} de {total_images} imagens processadas"
                    self.page.update()
                reading.finish_processing()
                self.app_state.persist_experiments()
            self.feedback_text.value = f"Experimento processado. {len(pending_items)} leituras atualizadas."
            self.feedback_text.color = "#86EFAC"
        except Exception as exc:
            self.feedback_text.value = f"Erro no processamento do experimento: {exc}"
            self.feedback_text.color = "#FCA5A5"
        self.progress_bar.visible = False
        self._request_refresh()

    async def _process_reading(self, reading, persist, label):
        self.progress_bar.visible = True
        self.progress_bar.value = 0
        self.process_button.disabled = True
        total = len(reading.images)
        try:
            for index, image in enumerate(reading.images, start=1):
                await self._process_image(image, reading.damage_mode)
                self.progress_bar.value = index / total
                self.feedback_text.value = f"{index} de {total} imagens processadas"
                self.page.update()
            reading.finish_processing()
            if persist:
                self.app_state.persist_experiments()
            self.feedback_text.value = f"{label.capitalize()} processado com sucesso."
            self.feedback_text.color = "#86EFAC"
        except Exception as exc:
            self.feedback_text.value = f"Erro no processamento: {exc}"
            self.feedback_text.color = "#FCA5A5"
        self.progress_bar.visible = False

    async def _process_image(self, image, damage_mode):
        if image.path is None:
            raise RuntimeError("Imagem temporária não encontrada.")
        result = await asyncio.to_thread(
            self.analysis_service.process_image,
            image_path=Path(image.path),
            confidence=self.app_state.settings.confidence,
            damage_mode=damage_mode,
        )
        image.view_sources = result["view_sources"]
        image.healthy_pct = result["healthy_pct"]
        image.severity_pct = result["severity_pct"]
        image.processed = True
        image.view_mode = "mapa"

    def _delete_current_image(self, _):
        reading = self.app_state.get_active_parcel()
        current = reading.current_image() if reading else None
        if reading is None or current is None:
            return
        if reading.processed:
            reading.invalidate_results()
        reading.images.remove(current)
        reading.current_index = min(reading.current_index, max(len(reading.images) - 1, 0))
        if not reading.validation_mode:
            self.app_state.persist_experiments()
        self.viewer_token = None
        self._request_refresh()

    def _previous_image(self, _):
        reading = self.app_state.get_active_parcel()
        if reading:
            reading.previous_image()
            self._reset_viewer_state()
            self._request_refresh()

    def _next_image(self, _):
        reading = self.app_state.get_active_parcel()
        if reading:
            reading.next_image()
            self._reset_viewer_state()
            self._request_refresh()

    def _change_view_mode(self, event):
        reading = self.app_state.get_active_parcel()
        if reading is None:
            return
        mode = event.control.value or "original"
        for image in reading.images:
            image.view_mode = mode if image.processed else "original"
        self._reset_viewer_state()
        self._request_refresh()

    def _start_unit_test(self, _):
        damage_mode = self._damage_mode_dropdown()

        def create(feedback):
            if not damage_mode.value:
                feedback.value = "Selecione o tipo de dano que será analisado."
                return False
            self.app_state.start_unit_test(damage_mode.value)
            self.view_mode_dropdown.value = "original"
            return True

        self._show_form_dialog("Novo teste unitário", [damage_mode], create)

    def _open_experiment(self, item_id):
        self.app_state.open_experiment(item_id)
        self._request_refresh()

    def _open_treatment(self, item_id):
        self.app_state.open_treatment(item_id)
        self._request_refresh()

    def _open_plot(self, item_id):
        self.app_state.open_plot(item_id)
        self._request_refresh()

    def _open_reading(self, item_id):
        self.app_state.open_reading(item_id)
        self.view_mode_dropdown.value = "original"
        self.viewer_token = None
        self._request_refresh()

    def _navigate_back(self, _):
        self.app_state.navigate_back()
        self.viewer_token = None
        self._request_refresh()

    def _start_pick_images(self, event):
        self.page.run_task(self._pick_images, event)

    def _start_capture_image(self, event):
        self.page.run_task(self._capture_image, event)

    def _start_load_test_images(self, event):
        self.page.run_task(self._load_test_images, event)

    def _start_process_unit_test(self, event):
        self.page.run_task(self._process_unit_test, event)

    def _start_process_experiment(self, event):
        self.page.run_task(self._process_experiment, event)

    def _experiment_ready_readings(self, experiment):
        return [
            (treatment, plot, reading)
            for treatment in experiment.treatments
            for plot in treatment.parcels
            for reading in plot.readings
            if reading.is_ready_to_process()
        ]

    def _reading_subtitle(self, reading):
        if reading.validation_mode:
            return f"Validação rápida • {reading.damage_mode_label}"
        status = "Processada" if reading.processed else f"alvo: {reading.target_images} imagens"
        return f"{reading.date} • {status} • {reading.damage_mode_label}"

    def _loaded_images_label(self, count, reading):
        return f"{count} {'imagem carregada' if count == 1 else 'imagens carregadas'}." if reading.validation_mode else f"{count}/{reading.target_images} imagens carregadas."

    def _normalize_date(self, value):
        text = (value or "").strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return None

    def _original_image_source(self, image):
        if not image.path:
            return ""
        try:
            return base64.b64encode(Path(image.path).read_bytes()).decode("ascii")
        except OSError:
            return ""

    def _content_width(self):
        return min(MAX_CONTENT_WIDTH, max(0, self.page.width or MAX_CONTENT_WIDTH))

    def _content_padding(self, width):
        return 14 if width < COMPACT_BREAKPOINT else 18

    def _body_width(self):
        width = self._content_width()
        return max(0, width - self._content_padding(width) * 2)

    def _viewer_size(self):
        return max(MIN_VIEWER_SIZE, min(DEFAULT_VIEWER_SIZE, self._body_width() - CARD_PADDING * 2))

    def _apply_responsive_sizes(self):
        body_width = self._body_width()
        viewer_size = self._viewer_size()
        self.process_button.width = body_width
        self.experiment_process_button.width = body_width
        self.view_mode_dropdown.width = max(MIN_VIEWER_SIZE, body_width - CARD_PADDING * 2)
        for control in (self.segmented_image, self.placeholder, self.viewer_stack):
            control.width = viewer_size
            control.height = viewer_size

    def _permission_handler_supported(self):
        return self.page.web or self.page.platform in {
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.ANDROID_TV,
            ft.PagePlatform.IOS,
            ft.PagePlatform.WINDOWS,
        }

    def _camera_capture_supported(self):
        return ft_camera is not None and (self.page.web or self.page.platform in {ft.PagePlatform.ANDROID, ft.PagePlatform.IOS})

    def _is_native_desktop(self):
        return not self.page.web and self.page.platform in {ft.PagePlatform.WINDOWS, ft.PagePlatform.LINUX, ft.PagePlatform.MACOS}

    def _sync_viewer_session(self, current):
        token = None if current is None else f"{current.id}:{current.view_mode}:{current.processed}"
        if token != self.viewer_token:
            self.viewer_token = token
            self._reset_viewer_state()

    def _reset_viewer_state(self):
        self.viewer_session_key = uuid.uuid4().hex

    def _set_feedback(self, message, error=False):
        self.feedback_text.value = message
        self.feedback_text.color = "#FCA5A5" if error else "#94A3B8"
        self.page.update()

    def _request_refresh(self):
        if callable(self.on_state_change):
            self.on_state_change()
        else:
            self.page.update()
