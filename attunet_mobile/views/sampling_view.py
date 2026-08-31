import uuid
import asyncio
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

from config import CULTURE_OPTIONS, WEB_IMAGE_BATCH_LIMIT, WEB_IMAGE_COMPRESSION_QUALITY
from services.image_service import (
    list_test_images_from_folder,
    pick_desktop_directory_path,
    pick_desktop_image_paths,
    prepare_selected_images,
    save_temp_image_bytes,
)
from state.app_state import ParcelImage


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
        if self.permission_handler is not None:
            self.page.services.append(self.permission_handler)
        self.camera = None
        self.camera_dialog = None
        self.camera_status_text = None
        self.viewer_token = None
        self.viewer_session_key = uuid.uuid4().hex

        self.feedback_text = ft.Text(
            "Faltam imagens para completar a parcela.",
            color="#94A3B8",
            size=13,
            text_align=ft.TextAlign.CENTER,
        )
        self.status_text = self.feedback_text
        self.selection_text = self.feedback_text
        self.progress_bar = ft.ProgressBar(value=0, color="#0B6E1B", bgcolor="#334155", visible=False)
        self.process_button = ft.FilledButton(
            "Processar Parcela",
            on_click=self._start_process_parcel,
            height=54,
            width=354,
        )
        self.save_button = ft.FilledButton(
            "Salvar Parcela",
            icon=ft.Icons.SAVE_ROUNDED,
            on_click=self._save_parcel,
            height=54,
            width=354,
        )
        self.view_mode_dropdown = ft.Dropdown(
            width=322,
            value="mapa",
            label="Modo de visualizacao",
            options=[
                ft.dropdown.Option("original", "Original"),
                ft.dropdown.Option("sobreposicao", "Sobreposicao"),
                ft.dropdown.Option("mapa", "Mapa"),
            ],
            on_select=self._change_view_mode,
            filled=True,
            fill_color="#111827",
            border_color="#334155",
            color="white",
        )
        self.current_healthy_text = ft.Text(
            "--",
            color="#86EFAC",
            size=28,
            weight=ft.FontWeight.W_700,
            text_align=ft.TextAlign.CENTER,
        )
        self.current_severity_text = ft.Text(
            "--",
            color="#FDBA74",
            size=28,
            weight=ft.FontWeight.W_700,
            text_align=ft.TextAlign.CENTER,
        )
        self.avg_healthy_text = ft.Text(
            "--",
            color="#D1FAE5",
            size=14,
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
        )
        self.avg_severity_text = ft.Text(
            "--",
            color="#FFEDD5",
            size=14,
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
        )
        self.segmented_image = ft.Image(
            src="",
            width=322,
            height=322,
            fit="contain",
            border_radius=16,
            visible=False,
        )
        self.placeholder = ft.Container(
            width=322,
            height=322,
            border_radius=16,
            bgcolor="#1F2937",
            alignment=ft.Alignment.CENTER,
            content=ft.Text(
                "Adicione imagens da parcela para iniciar o processamento.",
                color="#9AA4B2",
                size=15,
                text_align=ft.TextAlign.CENTER,
            ),
        )
        self.viewer_stack = ft.Stack(
            width=322,
            height=322,
            fit=ft.StackFit.EXPAND,
            controls=[
                self.placeholder,
                self.segmented_image,
            ],
        )

    def build(self):
        active_parcel = self.app_state.get_active_parcel()
        if active_parcel is None:
            return self._build_parcel_list()

        self._refresh_detail(active_parcel)
        return self._build_parcel_detail(active_parcel)

    def _build_parcel_list(self):
        parcels_controls = [self._parcel_card(parcel) for parcel in self.app_state.parcels]
        if not parcels_controls:
            parcels_controls = [
                ft.Container(
                    bgcolor="#1F2937",
                    border_radius=22,
                    padding=22,
                    content=ft.Text(
                        "Nenhuma parcela criada ainda. Use o botao + para adicionar uma nova amostragem.",
                        color="#C9D1D9",
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            ]

        return ft.Container(
            expand=True,
            width=390,
            padding=ft.Padding(left=18, top=18, right=18, bottom=24),
            alignment=ft.Alignment.TOP_CENTER,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                expand=True,
                                spacing=4,
                                controls=[
                                    ft.Text("Amostragens", size=24, weight=ft.FontWeight.W_700, color="white"),
                                    ft.Text(
                                        "Crie parcelas, adicione imagens e processe cada parcela separadamente.",
                                        size=15,
                                        color="#AAB2BF",
                                    ),
                                ],
                            ),
                            ft.FloatingActionButton(
                                icon=ft.Icons.ADD,
                                bgcolor="#1D4ED8",
                                mini=True,
                                on_click=self._open_add_parcel_dialog,
                            ),
                        ],
                    ),
                    *parcels_controls,
                ],
                spacing=16,
            ),
        )

    def _build_parcel_detail(self, parcel):
        action_controls = [
            self._action_card(
                icon=ft.Icons.PHOTO_LIBRARY_ROUNDED,
                title="Adicionar Imagens",
                subtitle="Selecione imagens da galeria ate completar a parcela.",
                on_click=self._start_pick_images,
            ),
        ]

        if self._camera_capture_supported():
            action_controls.append(
                self._action_card(
                    icon=ft.Icons.PHOTO_CAMERA_ROUNDED,
                    title="Fotografar",
                    subtitle="Abra a camera traseira do dispositivo e adicione uma imagem por vez.",
                    on_click=self._start_capture_image,
                )
            )

        if self.page.platform in {
            ft.PagePlatform.WINDOWS,
            ft.PagePlatform.LINUX,
            ft.PagePlatform.MACOS,
        }:
            action_controls.append(
                self._action_card(
                    icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                    title="Usar imagens_teste",
                    subtitle="Apenas para teste em desktop.",
                    on_click=self._start_load_test_images,
                )
            )

        return ft.Container(
            expand=True,
            width=390,
            padding=ft.Padding(left=18, top=18, right=18, bottom=24),
            alignment=ft.Alignment.TOP_CENTER,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.START,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                icon_color="white",
                                on_click=self._back_to_list,
                            ),
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text(parcel.name, size=22, weight=ft.FontWeight.W_700, color="white"),
                                    ft.Text(
                                        self._parcel_detail_header(parcel),
                                        color="#AAB2BF",
                                        size=14,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Text(parcel.description or "Sem descricao adicional.", size=14, color="#94A3B8"),
                    *action_controls,
                    self._feedback_line(),
                    self.process_button,
                    self.progress_bar,
                    self._viewer_card(),
                    self._metrics_card(),
                    self._view_mode_card(),
                    self.save_button,
                ],
                spacing=16,
            ),
        )

    def _refresh_detail(self, parcel):
        current = parcel.current_image()
        image_count = len(parcel.images)
        remaining = parcel.remaining_images()
        self.feedback_text.color = "#94A3B8"
        self.process_button.disabled = not parcel.is_ready_to_process()
        self.save_button.disabled = not any(image.processed for image in parcel.images)

        if image_count == 0:
            if parcel.validation_mode:
                self.selection_text.value = "Adicione uma ou mais imagens para processar a parcela."
            else:
                self.selection_text.value = f"Faltam {parcel.target_images} imagens para completar a parcela."
            self.segmented_image.visible = False
            self.placeholder.visible = True
            self.placeholder.content.value = "Adicione imagens da parcela para iniciar o processamento."
            self.view_mode_dropdown.disabled = True
            self.current_healthy_text.value = "--"
            self.current_severity_text.value = "--"
            self.avg_healthy_text.value = "--"
            self.avg_severity_text.value = "--"
            self._sync_viewer_session(None)
            return

        if parcel.validation_mode:
            self.selection_text.value = self._loaded_images_label(image_count)
        elif remaining and remaining > 0:
            plural = "imagem" if remaining == 1 else "imagens"
            self.selection_text.value = f"Faltam {remaining} {plural} para completar a parcela."
        else:
            self.selection_text.value = "Parcela completa. Use pinca para zoom e dois toques laterais para trocar a imagem."
        self.view_mode_dropdown.disabled = False
        self.avg_healthy_text.value = f"{parcel.average_healthy_pct():.2f}%"
        self.avg_severity_text.value = f"{parcel.average_severity_pct():.2f}%"

        if current is None:
            self._sync_viewer_session(None)
            return

        self._sync_viewer_session(current)
        self.view_mode_dropdown.value = current.view_mode or self._active_view_mode()
        if current.has_visualization and current.view_sources.get(current.view_mode):
            self.segmented_image.src = current.view_sources[current.view_mode]
            self.segmented_image.visible = True
            self.placeholder.visible = False
        else:
            self.segmented_image.src = ""
            self.segmented_image.visible = False
            self.placeholder.visible = True
            if current.processed:
                self.placeholder.content.value = "As imagens sao perdidas apos fechamento do aplicativo."
            else:
                self.placeholder.content.value = "Imagem ainda nao processada."

        if current.processed:
            self.current_healthy_text.value = f"{current.healthy_pct:.2f}%"
            self.current_severity_text.value = f"{current.severity_pct:.2f}%"
        else:
            self.current_healthy_text.value = "--"
            self.current_severity_text.value = "--"

    async def _pick_images(self, _):
        try:
            parcel = self.app_state.get_active_parcel()
            if parcel is None:
                return
            remaining = parcel.remaining_images()
            if remaining == 0:
                self.status_text.value = "A parcela ja atingiu a quantidade alvo de imagens."
                self.page.update()
                return

            if self._is_native_desktop():
                selected_files = await asyncio.to_thread(pick_desktop_image_paths)
                if not selected_files:
                    return
                if remaining is not None:
                    selected_files = selected_files[:remaining]
                paths = prepare_selected_images(
                    selected_files,
                    optimize_for_web=False,
                    copy_local_files=False,
                )
            else:
                files = await self.file_picker.pick_files(
                    allow_multiple=True,
                    file_type=ft.FilePickerFileType.IMAGE,
                    with_data=self.page.web,
                    compression_quality=WEB_IMAGE_COMPRESSION_QUALITY if self.page.web else 0,
                )
                if not files:
                    return

                selected_files = files if remaining is None else files[:remaining]
                if self.page.web and remaining is not None:
                    selected_files = selected_files[: min(remaining, WEB_IMAGE_BATCH_LIMIT)]
                elif self.page.web:
                    selected_files = selected_files[:WEB_IMAGE_BATCH_LIMIT]

                paths = prepare_selected_images(
                    selected_files,
                    optimize_for_web=self.page.web,
                    copy_local_files=True,
                )

            if not paths:
                self.status_text.value = "Nao foi possivel carregar as imagens selecionadas."
                self.page.update()
                return

            for path in paths:
                parcel.images.append(
                    ParcelImage(
                        id=uuid.uuid4().hex,
                        path=str(path),
                        view_mode=self._active_view_mode(),
                    )
                )
            self.status_text.value = self._loaded_images_label(len(parcel.images), parcel)
            self._request_refresh()
        except RuntimeError as exc:
            self.status_text.value = f"Erro ao abrir seletor de imagens: {exc}"
            self.page.update()
        except Exception as exc:
            self.status_text.value = f"Erro ao carregar imagens: {exc}"
            self.page.update()

    async def _capture_image(self, _):
        parcel = self.app_state.get_active_parcel()
        if parcel is None:
            return
        remaining = parcel.remaining_images()
        if remaining == 0:
            self.status_text.value = "A parcela ja atingiu a quantidade alvo de imagens."
            self.page.update()
            return

        if ft_camera is None:
            self.status_text.value = "Suporte de camera nao instalado nesta versao do aplicativo."
            self.page.update()
            return

        if self.permission_handler is None:
            self.status_text.value = "Servico de permissao nao esta disponivel nesta versao do aplicativo."
            self.page.update()
            return

        permission_status = await self.permission_handler.get_status(fph.Permission.CAMERA)
        if permission_status != fph.PermissionStatus.GRANTED:
            permission_status = await self.permission_handler.request(fph.Permission.CAMERA)

        if permission_status != fph.PermissionStatus.GRANTED:
            self.status_text.value = "Permissao de camera negada. Libere a camera para fotografar a parcela."
            self.page.update()
            return

        await self._open_camera_dialog()

    async def _open_camera_dialog(self):
        self.camera_status_text = ft.Text("Inicializando camera...", color="#C9D1D9", text_align=ft.TextAlign.CENTER)
        self.camera = ft_camera.Camera(
            expand=True,
            preview_enabled=True,
        )

        def close_dialog(_=None):
            self.camera = None
            self.camera_status_text = None
            self.page.pop_dialog()
            self.page.update()

        self.camera_dialog = ft.AlertDialog(
            modal=True,
            bgcolor="#111827",
            title=ft.Text("Fotografar Parcela", color="white"),
            content=ft.Container(
                width=320,
                height=420,
                content=ft.Column(
                    tight=True,
                    controls=[
                        ft.Container(
                            expand=True,
                            border_radius=16,
                            clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            bgcolor="#020617",
                            content=self.camera,
                        ),
                        self.camera_status_text,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=close_dialog),
                ft.FilledButton("Capturar", icon=ft.Icons.CAMERA_ALT_ROUNDED, on_click=self._take_camera_picture),
            ],
        )
        self.page.show_dialog(self.camera_dialog)
        self.page.update()

        try:
            cameras = await self.camera.get_available_cameras()
            if not cameras:
                raise RuntimeError("Nenhuma camera disponivel no dispositivo.")
            selected_camera = next(
                (
                    item
                    for item in cameras
                    if item.lens_direction == ft_camera.CameraLensDirection.BACK
                ),
                cameras[0],
            )
            await self.camera.initialize(
                description=selected_camera,
                resolution_preset=ft_camera.ResolutionPreset.HIGH,
                enable_audio=False,
            )
            self.camera_status_text.value = "Camera traseira pronta."
        except Exception as exc:
            self.camera_status_text.value = f"Erro ao iniciar camera: {exc}"
        self.page.update()

    async def _take_camera_picture(self, _):
        parcel = self.app_state.get_active_parcel()
        if parcel is None or self.camera is None:
            return

        try:
            image_bytes = await self.camera.take_picture()
            target_path = save_temp_image_bytes(
                file_bytes=image_bytes,
                file_name=f"camera_{len(parcel.images) + 1}.jpg",
                index=len(parcel.images),
            )
        except Exception as exc:
            if self.camera_status_text is not None:
                self.camera_status_text.value = f"Erro ao capturar imagem: {exc}"
                self.page.update()
            return

        parcel.images.append(
            ParcelImage(
                id=uuid.uuid4().hex,
                path=str(target_path),
                view_mode=self._active_view_mode(),
            )
        )
        self.status_text.value = self._loaded_images_label(len(parcel.images), parcel)
        self.camera = None
        self.camera_status_text = None
        self.page.pop_dialog()
        self._request_refresh()

    async def _load_test_images(self, _):
        try:
            parcel = self.app_state.get_active_parcel()
            if parcel is None:
                return
            remaining = parcel.remaining_images()
            if remaining == 0:
                self.status_text.value = "A parcela ja atingiu a quantidade alvo de imagens."
                self.page.update()
                return

            source_paths = []
            if self._is_native_desktop():
                folder_path = await self._pick_test_folder()
                if folder_path is None:
                    return
                source_paths, error_message = list_test_images_from_folder(folder_path)
                if error_message:
                    self.status_text.value = error_message
                    self.page.update()
                    return
            else:
                self.status_text.value = "Usar imagens_teste esta disponivel apenas no desktop."
                self.page.update()
                return

            selected_paths = source_paths if remaining is None else source_paths[:remaining]
            paths = prepare_selected_images(
                selected_paths,
                optimize_for_web=False,
                copy_local_files=False,
            )
            if not paths:
                self.status_text.value = "Nenhuma imagem valida foi carregada da pasta selecionada."
                self.page.update()
                return

            for path in paths:
                parcel.images.append(
                    ParcelImage(
                        id=uuid.uuid4().hex,
                        path=str(path),
                        view_mode=self._active_view_mode(),
                    )
                )
            self.status_text.value = self._loaded_images_label(len(parcel.images), parcel)
            self._request_refresh()
        except Exception as exc:
            self.status_text.value = f"Erro ao carregar pasta de teste: {exc}"
            self.page.update()

    def _start_pick_images(self, event):
        self.page.run_task(self._pick_images, event)

    def _start_capture_image(self, event):
        self.page.run_task(self._capture_image, event)

    def _start_load_test_images(self, event):
        self.page.run_task(self._load_test_images, event)

    def _start_process_parcel(self, event):
        self.page.run_task(self._process_parcel, event)

    async def _process_parcel(self, _):
        parcel = self.app_state.get_active_parcel()
        if parcel is None:
            return
        if not parcel.is_ready_to_process():
            self.status_text.value = "Carregue todas as imagens da parcela antes de processar."
            self.page.update()
            return

        try:
            total = len(parcel.images)
            self.progress_bar.visible = True
            self.progress_bar.value = 0
            self.process_button.disabled = True
            self.status_text.value = f"0 de {total} imagens processadas | faltam {total}"
            self.page.update()

            for index, image in enumerate(parcel.images, start=1):
                if image.path is None:
                    continue
                remaining = max(total - index, 0)
                self.status_text.value = f"{index - 1} de {total} imagens processadas | faltam {remaining + 1}"
                self.page.update()

                result = await asyncio.to_thread(
                    self.analysis_service.process_image,
                    image_path=Path(image.path),
                    confidence=self.app_state.settings.confidence,
                    sensitivity=self.app_state.settings.sensitivity,
                    use_hybrid_threshold=self.app_state.settings.use_hybrid_threshold,
                )
                image.view_sources = result["view_sources"]
                image.healthy_pct = result["healthy_pct"]
                image.severity_pct = result["severity_pct"]
                image.processed = True
                self.progress_bar.value = index / total
                self.status_text.value = f"{index} de {total} imagens processadas | faltam {remaining}"
                self.page.update()

            self.status_text.value = "Parcela processada com sucesso."
        except Exception as exc:
            self.status_text.value = f"Erro no processamento da parcela: {exc}"
        self.progress_bar.visible = False
        self._request_refresh()

    def _save_parcel(self, _):
        parcel = self.app_state.get_active_parcel()
        if parcel is None:
            return
        self.app_state.save_parcel(parcel.id)
        self.feedback_text.value = "Parcela salva com sucesso."
        self.feedback_text.color = "#86EFAC"
        self.status_text.value = "Parcela salva. Ao reabrir, apenas os resultados percentuais serao mantidos."
        self.page.update()

    def _previous_image(self, _):
        parcel = self.app_state.get_active_parcel()
        if parcel is None:
            return
        parcel.previous_image()
        self._reset_viewer_state()
        self._request_refresh()

    def _next_image(self, _):
        parcel = self.app_state.get_active_parcel()
        if parcel is None:
            return
        parcel.next_image()
        self._reset_viewer_state()
        self._request_refresh()

    def _change_view_mode(self, event):
        parcel = self.app_state.get_active_parcel()
        if parcel is None:
            return
        selected_mode = event.control.value or "mapa"
        self.view_mode_dropdown.value = selected_mode
        self._apply_view_mode_to_parcel(parcel, selected_mode)
        self._reset_viewer_state()
        self._request_refresh()

    def _open_add_parcel_dialog(self, _):
        name_field = ft.TextField(label="Nome da parcela", autofocus=True)
        target_field = ft.TextField(label="Quantidade alvo de imagens", value="3", keyboard_type=ft.KeyboardType.NUMBER)

        def toggle_validation_mode(_):
            target_field.visible = not bool(validation_checkbox.value)
            self.page.update()

        validation_checkbox = ft.Checkbox(
            label="Testes de Validacao",
            value=False,
            check_color="white",
            active_color="#4ADE80",
            label_style=ft.TextStyle(color="white"),
            on_change=toggle_validation_mode,
        )
        date_field = ft.TextField(label="Data", value=date.today().strftime("%d/%m/%Y"))
        culture_dropdown = ft.Dropdown(
            label="Cultura",
            value=CULTURE_OPTIONS[0],
            options=[ft.dropdown.Option(option) for option in CULTURE_OPTIONS],
            on_select=lambda e: None,
        )
        description_field = ft.TextField(label="Descricao", multiline=True, min_lines=2, max_lines=3)
        feedback_text = ft.Text("", color="#FCA5A5")

        def close_dialog(_=None):
            self.page.pop_dialog()
            self.page.update()

        def create_parcel(_):
            if not name_field.value.strip():
                feedback_text.value = "Informe o nome da parcela."
                self.page.update()
                return
            validation_mode = bool(validation_checkbox.value)
            if validation_mode:
                target_images = 0
            else:
                try:
                    target_images = int(target_field.value)
                except (TypeError, ValueError):
                    feedback_text.value = "Informe um numero valido de imagens."
                    self.page.update()
                    return
                if target_images <= 0:
                    feedback_text.value = "A quantidade alvo deve ser maior que zero."
                    self.page.update()
                    return
            formatted_date = self._normalize_parcel_date(date_field.value)
            if formatted_date is None:
                feedback_text.value = "Informe a data no formato DD/MM/AAAA."
                self.page.update()
                return

            parcel = self.app_state.add_parcel(
                name=name_field.value.strip(),
                target_images=target_images,
                date=formatted_date,
                culture=culture_dropdown.value or CULTURE_OPTIONS[0],
                description=description_field.value.strip(),
                validation_mode=validation_mode,
            )
            self.app_state.open_parcel(parcel.id)
            close_dialog()
            self._request_refresh()

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor="#1F2937",
            title=ft.Text("Nova Parcela", color="white"),
            content=ft.Column(
                tight=True,
                controls=[
                    name_field,
                    validation_checkbox,
                    target_field,
                    date_field,
                    culture_dropdown,
                    description_field,
                    feedback_text,
                ],
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=close_dialog),
                ft.FilledButton("Criar", on_click=create_parcel),
            ],
        )
        self.page.show_dialog(dialog)

    def _back_to_list(self, _):
        self.app_state.close_parcel()
        self.viewer_token = None
        self._reset_viewer_state()
        self._request_refresh()

    def _open_parcel(self, parcel_id: str):
        self.app_state.open_parcel(parcel_id)
        self.view_mode_dropdown.value = "mapa"
        parcel = self.app_state.get_active_parcel()
        if parcel is not None:
            self._apply_view_mode_to_parcel(parcel, "mapa")
        self.viewer_token = None
        self._reset_viewer_state()
        self._request_refresh()

    def _delete_parcel(self, parcel_id: str):
        self.app_state.delete_parcel(parcel_id)
        self._request_refresh()

    def _parcel_card(self, parcel):
        processed_images = sum(1 for image in parcel.images if image.processed)
        return ft.Container(
            bgcolor="#1F2937",
            border_radius=22,
            padding=16,
            on_click=lambda _: self._open_parcel(parcel.id),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=58,
                        height=58,
                        border_radius=16,
                        bgcolor="#0B6E1B",
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(ft.Icons.GRID_VIEW_ROUNDED, color="white", size=28),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            ft.Text(parcel.name, color="white", size=20, weight=ft.FontWeight.W_700),
                            ft.Text(
                                f"{parcel.culture} | {self._format_parcel_date(parcel.date)}",
                                color="#AAB2BF",
                                size=14,
                            ),
                            ft.Text(
                                "Testes de Validacao" if parcel.validation_mode else f"Alvo: {parcel.target_images} imagens",
                                color="#CBD5E1",
                                size=13,
                            ),
                            ft.Text(
                                self._processed_images_label(processed_images),
                                color="#CBD5E1",
                                size=13,
                            ),
                            ft.Text(
                                f"Media parcela - sadia {parcel.average_healthy_pct():.2f}% | severidade {parcel.average_severity_pct():.2f}%",
                                color="#94A3B8",
                                size=12,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                        icon_color="#FCA5A5",
                        on_click=lambda _: self._delete_parcel(parcel.id),
                    ),
                ],
            ),
        )

    def _action_card(self, icon, title: str, subtitle: str, on_click):
        return ft.Container(
            bgcolor="#1F2937",
            border_radius=22,
            padding=16,
            on_click=on_click,
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=58,
                        height=58,
                        border_radius=16,
                        bgcolor="#0B6E1B",
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon, color="white", size=28),
                    ),
                    ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            ft.Text(title, color="white", size=20, weight=ft.FontWeight.W_700),
                            ft.Text(subtitle, color="#AAB2BF", size=14),
                        ],
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color="#C9D1D9"),
                ],
            ),
        )

    def _status_card(self):
        return ft.Container(
            bgcolor="#1F2937",
            border_radius=22,
            padding=16,
            width=354,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
                controls=[
                    ft.Text("Status", color="white", size=18, weight=ft.FontWeight.W_700),
                    self.status_text,
                    self.selection_text,
                ],
            ),
        )

    def _feedback_line(self):
        return ft.Container(
            width=354,
            padding=ft.Padding(left=10, top=0, right=10, bottom=0),
            content=self.feedback_text,
        )

    def _viewer_card(self):
        parcel = self.app_state.get_active_parcel()
        image_count = len(parcel.images) if parcel is not None else 0
        interactive_viewer = ft.InteractiveViewer(
            key=self.viewer_session_key,
            content=ft.Container(
                width=322,
                height=322,
                alignment=ft.Alignment.CENTER,
                content=self.viewer_stack,
            ),
            min_scale=1.0,
            max_scale=5.0,
            boundary_margin=96,
            interaction_update_interval=16,
            scale_factor=120,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        return ft.Container(
            bgcolor="#111827",
            border_radius=22,
            padding=16,
            width=354,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Stack(
                width=322,
                height=322,
                fit=ft.StackFit.EXPAND,
                controls=[
                    interactive_viewer,
                    ft.Container(
                        left=8,
                        top=136,
                        visible=image_count > 1,
                        content=self._viewer_nav_zone(
                            icon=ft.Icons.CHEVRON_LEFT_ROUNDED,
                            on_click=self._previous_image,
                        ),
                    ),
                    ft.Container(
                        right=8,
                        top=136,
                        visible=image_count > 1,
                        content=self._viewer_nav_zone(
                            icon=ft.Icons.CHEVRON_RIGHT_ROUNDED,
                            on_click=self._next_image,
                        ),
                    ),
                ],
            ),
        )

    def _view_mode_card(self):
        return ft.Container(
            bgcolor="#1F2937",
            border_radius=22,
            padding=16,
            width=354,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text("Visualizacao", color="white", size=18, weight=ft.FontWeight.W_700),
                    self.view_mode_dropdown,
                ],
            ),
        )

    def _metrics_card(self):
        return ft.Container(
            bgcolor="#1F2937",
            border_radius=22,
            padding=16,
            width=354,
            content=ft.Row(
                spacing=12,
                controls=[
                    self._metric_box(
                        "Area Sadia",
                        self.current_healthy_text,
                        self.avg_healthy_text,
                        "#0F2A1C",
                        "#1C8B4A",
                    ),
                    self._metric_box(
                        "Severidade",
                        self.current_severity_text,
                        self.avg_severity_text,
                        "#2D190F",
                        "#D97706",
                    ),
                ],
            ),
        )

    def _metric_box(self, title: str, value_control: ft.Text, average_control: ft.Text, bg_color: str, border_color: str):
        border_side = ft.border.BorderSide(width=1, color=border_color)
        return ft.Container(
            expand=True,
            border_radius=18,
            bgcolor=bg_color,
            border=ft.border.Border(
                left=border_side,
                top=border_side,
                right=border_side,
                bottom=border_side,
            ),
            padding=14,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Text(title, color="white", size=15, weight=ft.FontWeight.W_700),
                    ft.Text("Imagem aberta", color="#CBD5E1", size=12),
                    value_control,
                    ft.Text("Media do lote", color="#94A3B8", size=11),
                    average_control,
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
                bgcolor="#0F172A99",
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(icon, color="#E5E7EB", size=20),
            ),
        )

    def _permission_handler_supported(self):
        return self.page.web or self.page.platform in {
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.ANDROID_TV,
            ft.PagePlatform.IOS,
            ft.PagePlatform.WINDOWS,
        }

    def _camera_capture_supported(self):
        return ft_camera is not None and (
            self.page.web or self.page.platform in {
                ft.PagePlatform.ANDROID,
                ft.PagePlatform.IOS,
            }
        )

    def _is_native_desktop(self):
        return (not self.page.web) and self.page.platform in {
            ft.PagePlatform.WINDOWS,
            ft.PagePlatform.LINUX,
            ft.PagePlatform.MACOS,
        }

    async def _pick_test_folder(self):
        if self._is_native_desktop():
            return await asyncio.to_thread(pick_desktop_directory_path)
        try:
            selected = await self.file_picker.get_directory_path(
                dialog_title="Selecionar pasta com imagens de teste"
            )
        except RuntimeError as exc:
            self.status_text.value = f"Erro ao abrir seletor de pasta: {exc}"
            self.page.update()
            return None
        if not selected:
            return None
        return Path(selected)

    def _sync_viewer_session(self, current):
        token = None
        if current is not None:
            token = f"{current.id}:{current.view_mode}:{bool(current.view_sources.get(current.view_mode))}"
        if token != self.viewer_token:
            self.viewer_token = token
            self._reset_viewer_state()

    def _reset_viewer_state(self):
        self.viewer_session_key = uuid.uuid4().hex

    def _active_view_mode(self):
        return self.view_mode_dropdown.value or "mapa"

    def _apply_view_mode_to_parcel(self, parcel, view_mode: str):
        for image in parcel.images:
            image.view_mode = view_mode

    def _normalize_parcel_date(self, value: str):
        text = (value or "").strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return None

    def _format_parcel_date(self, value: str):
        formatted = self._normalize_parcel_date(value)
        return formatted or (value or "")

    def _parcel_detail_header(self, parcel):
        if parcel.validation_mode:
            return f"{parcel.culture} | {self._format_parcel_date(parcel.date)} | Testes de Validacao"
        return f"{parcel.culture} | {self._format_parcel_date(parcel.date)} | alvo: {parcel.target_images} imagens"

    def _loaded_images_label(self, image_count: int, parcel=None):
        target_parcel = parcel or self.app_state.get_active_parcel()
        if target_parcel is not None and not target_parcel.validation_mode:
            return f"{image_count}/{target_parcel.target_images} imagens carregadas."
        if image_count == 1:
            return "1 imagem carregada."
        return f"{image_count} imagens carregadas."

    def _processed_images_label(self, processed_images: int):
        if processed_images == 1:
            return "1 imagem processada"
        return f"{processed_images} imagens processadas"

    def _request_refresh(self):
        if callable(self.on_state_change):
            self.on_state_change()
        else:
            self.page.update()
