# utils/eps_converter.py
import os
import logging
from pathlib import Path
from PIL import Image
import glob

logger = logging.getLogger(__name__)


class EPSConverter:
    """Конвертер EPS файлов в PNG с кэшированием"""

    def __init__(self, sim_dir: str):
        self.sim_dir = Path(sim_dir)
        self.plots_dir = self.sim_dir / "plots"
        self.png_dir = self.sim_dir / "plots_png"
        self.png_dir.mkdir(exist_ok=True)

    def get_available_plots(self) -> list:
        """Возвращает список всех EPS файлов для конвертации"""
        eps_files = []

        # Ищем в корне симуляции
        eps_files.extend(glob.glob(str(self.sim_dir / "*.eps")))

        # Ищем в папке plots
        if self.plots_dir.exists():
            eps_files.extend(glob.glob(str(self.plots_dir / "*.eps")))

        # Убираем дубликаты и сортируем
        eps_files = sorted(list(set(eps_files)))

        logger.info(f"Найдено EPS файлов: {len(eps_files)}")
        for f in eps_files:
            logger.info(f"  - {os.path.basename(f)}")

        return eps_files

    def get_conversion_status(self) -> dict:
        """Возвращает статус конвертации: сколько EPS, сколько уже есть PNG"""
        eps_files = self.get_available_plots()

        if not eps_files:
            logger.info("get_conversion_status: нет EPS файлов")
            return {"total": 0, "converted": 0, "pending": 0, "percent": 0}

        converted_count = 0
        for eps_path in eps_files:
            eps_filename = os.path.basename(eps_path)
            png_filename = eps_filename.replace('.eps', '.png')
            png_path = self.png_dir / png_filename
            if png_path.exists():
                converted_count += 1
                logger.debug(f"PNG уже существует: {png_path}")
            else:
                logger.debug(f"PNG не существует: {png_path}")

        result = {
            "total": len(eps_files),
            "converted": converted_count,
            "pending": len(eps_files) - converted_count,
            "percent": int((converted_count / len(eps_files)) * 100) if eps_files else 0
        }
        logger.info(f"Статус конвертации: {result}")
        return result

    def convert_eps_to_png(self, eps_path: str, force: bool = False) -> str | None:
        """Конвертирует один EPS файл в PNG, сохраняет в plots_png"""
        eps_filename = os.path.basename(eps_path)
        png_filename = eps_filename.replace('.eps', '.png')
        png_path = str(self.png_dir / png_filename)

        if not force and os.path.exists(png_path):
            logger.debug(f"PNG уже существует: {png_path}")
            return png_path

        try:
            logger.info(f"Конвертация: {eps_filename}")
            img = Image.open(eps_path)
            # Сохраняем напрямую в plots_png
            img.save(png_path, 'PNG', dpi=(100, 100))
            logger.info(f"  -> сохранён: {png_path}")
            return png_path
        except Exception as e:
            logger.error(f"Ошибка конвертации {eps_path}: {e}")
            return None

    def convert_all_plots(self, force: bool = False, progress_callback=None) -> dict:
        """Конвертирует все найденные EPS файлы, возвращает словарь с результатами"""
        eps_files = self.get_available_plots()

        if not eps_files:
            return {"success": False, "message": "EPS файлы не найдены", "plots": [],
                    "progress": {"total": 0, "converted": 0, "percent": 100}}

        converted = []
        failed = []
        total = len(eps_files)

        for i, eps_path in enumerate(eps_files, 1):
            png_path = self.convert_eps_to_png(eps_path, force)
            if png_path:
                converted.append({
                    "eps": eps_path,
                    "png": png_path,
                    "name": self._get_plot_name(eps_path)
                })
            else:
                failed.append(eps_path)

            # Вызываем callback для обновления прогресса
            if progress_callback:
                progress_callback(i, total, len(converted), len(failed))

        logger.info(f"Конвертировано {len(converted)} из {len(eps_files)} графиков")

        return {
            "success": len(converted) > 0,
            "message": f"Конвертировано {len(converted)} из {len(eps_files)} графиков",
            "plots": converted,
            "failed": failed,
            "progress": {
                "total": total,
                "converted": len(converted),
                "percent": int((len(converted) / total) * 100) if total > 0 else 100
            }
        }

    def _get_plot_name(self, filepath: str) -> str:
        """Извлекает человеко-читаемое имя из имени файла"""
        basename = os.path.basename(filepath).replace('.eps', '')

        name_map = {
            'plot_1': 'Сетка',
            'plot_2': 'Функция ψ',
            'plot_3': 'Поле скорости',
            'plot_4': 'Давление (p)',
            'plot_5': 'Давление (изолинии)',
            'temp_final': 'Температурное поле (финальное)',
            'Mesh': 'Сетка',
            'Psi': 'Функция ψ',
            'Velocity': 'Поле скорости',
            'Contour': 'Контур',
            'Pressure': 'Давление',
        }

        if basename in name_map:
            return name_map[basename]

        if basename.startswith('plot_'):
            num = basename.replace('plot_', '')
            if num.isdigit():
                return f'График {num}'
            return basename.replace('_', ' ').title()

        if basename.startswith('temp_'):
            num = basename.replace('temp_', '')
            if num.isdigit():
                return f'Температурное поле (кадр {num})'
            return basename.replace('_', ' ').title()

        if basename.startswith('sig'):
            return f'Напряжения - {basename}'

        return basename.replace('_', ' ').title()

    def cleanup_png(self):
        """Удаляет все сгенерированные PNG файлы"""
        import shutil
        if self.png_dir.exists():
            shutil.rmtree(self.png_dir)
            self.png_dir.mkdir(exist_ok=True)