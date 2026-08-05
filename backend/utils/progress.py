import sys
import time


class ConsoleProgressBar:
    """Spyder/IPython 콘솔에서 사용할 단일 줄 진행바입니다."""

    def __init__(
        self,
        title: str,
        width: int = 28,
        minimum_interval: float = 0.05,
    ) -> None:
        self.title = str(title).strip()
        self.width = max(10, int(width))
        self.minimum_interval = max(
            0.0,
            float(minimum_interval),
        )
        self.started_at = time.monotonic()
        self.last_printed_at = 0.0
        self.last_percent = -1
        self.finished = False

    def update(
        self,
        percent: float,
        message: str = "",
    ) -> None:
        if self.finished:
            return

        numeric_percent = max(
            0.0,
            min(100.0, float(percent)),
        )
        integer_percent = int(round(numeric_percent))
        now = time.monotonic()

        should_print = (
            integer_percent != self.last_percent
            or numeric_percent >= 100
            or now - self.last_printed_at
            >= self.minimum_interval
        )

        if not should_print:
            return

        filled = int(
            self.width * numeric_percent / 100
        )
        bar = (
            "█" * filled
            + "░" * (self.width - filled)
        )
        elapsed = now - self.started_at
        detail = str(message).strip()

        line = (
            f"\r{self.title} "
            f"[{bar}] "
            f"{integer_percent:3d}% "
            f"| {elapsed:5.1f}초"
        )

        if detail:
            line += f" | {detail}"

        # 이전에 더 긴 문장이 출력됐을 때 남는 글자를 지웁니다.
        line = line.ljust(150)

        sys.stdout.write(line)
        sys.stdout.flush()

        self.last_percent = integer_percent
        self.last_printed_at = now

    def finish(self, message: str = "완료") -> None:
        if self.finished:
            return

        self.update(100, message)
        sys.stdout.write("\n")
        sys.stdout.flush()
        self.finished = True

    def fail(self, message: str = "실패") -> None:
        if self.finished:
            return

        elapsed = time.monotonic() - self.started_at
        sys.stdout.write(
            f"\r{self.title} [중단] "
            f"| {elapsed:5.1f}초 | {message}"
            .ljust(150)
            + "\n"
        )
        sys.stdout.flush()
        self.finished = True
