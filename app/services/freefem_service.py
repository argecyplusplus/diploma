import os
import subprocess
import shlex
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def run_freefem(edp_file_path: str, work_dir: str = None) -> dict:
    """
    Запускает FreeFEM++ в безоконном режиме.
    Возвращает: {success: bool, stdout: str, stderr: str, returncode: int}
    """
    ff_path = os.getenv('FREEFEM_PATH', 'FreeFem++')

    # Если путь указан, но файл не существует, пробуем найти в PATH
    if ff_path and ff_path != 'FreeFem++' and not os.path.exists(ff_path):
        logger.warning(f"FreeFEM не найден по пути: {ff_path}. Пробуем системный PATH.")
        ff_path = 'FreeFem++'

    # Формируем команду. -nw = no window (тихий режим)
    # На Windows иногда нужен FreeFem++-mpi.exe, но стандартный работает для .edp
    cmd = [ff_path, edp_file_path, "-nw"]

    # Для Windows пути с пробелами shlex не нужен, но список аргументов безопасен
    if os.name == 'nt':
        cmd = [ff_path, edp_file_path, "-nw"]

    env = os.environ.copy()
    if work_dir:
        env['PWD'] = work_dir

    try:
        logger.info(f"Запуск FreeFEM: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 минут максимум
            env=env,
            cwd=work_dir or os.path.dirname(edp_file_path)
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Превышено время выполнения (10 мин)"}
    except FileNotFoundError:
        return {"success": False, "error": f"FreeFEM++ не найден. Проверьте путь: {ff_path}"}
    except Exception as e:
        logger.error(f"Ошибка запуска FreeFEM: {e}")
        return {"success": False, "error": str(e)}