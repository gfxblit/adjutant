import json
import subprocess
from datetime import datetime
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable
from textual.containers import Container
from textual.reactive import reactive
from textual import work

from adjutant.engine import get_active_scvs, get_project_root, format_duration

class MissionSummary(Static):
    summary_data = reactive({})

    def render(self) -> str:
        if not self.summary_data:
            return "Loading mission summary..."
        
        s = self.summary_data
        total = s.get("total_issues", 0)
        open_ = s.get("open_issues", 0)
        closed = s.get("closed_issues", 0)
        in_progress = s.get("in_progress_issues", 0)
        ready = s.get("ready_issues", 0)
        blocked = s.get("blocked_issues", 0)
        
        progress = (closed / total * 100) if total > 0 else 0
        
        # Simple progress bar
        bar_width = 30
        filled_width = int(progress / 100 * bar_width)
        bar = "█" * filled_width + "░" * (bar_width - filled_width)
        
        counts = [
            f"[yellow]Open: {open_}[/]",
            f"[blue]In Progress: {in_progress}[/]",
            f"[green]Ready: {ready}[/]",
            f"[white]Closed: {closed}[/]"
        ]
        if blocked > 0:
            counts.append(f"[red]Blocked: {blocked}[/]")
            
        return (
            f"[b]Mission Summary[/b]\n"
            f"Progress: |{bar}| {progress:.1f}% ({closed}/{total})\n"
            f"{' | '.join(counts)}"
        )


class SCVTable(DataTable):
    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("Objective ID", "Agent", "PID", "Model", "Duration")


class AdjutantDashboard(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #summary-container {
        height: auto;
        padding: 1;
        background: $panel;
        margin: 1;
        border: solid $primary;
    }
    #scv-container {
        height: 1fr;
        padding: 1;
        margin: 1;
        border: solid $secondary;
    }
    DataTable {
        height: 1fr;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_data", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="summary-container"):
            yield MissionSummary(id="mission-summary")
        with Container(id="scv-container"):
            yield SCVTable(id="scv-table")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Adjutant TUI Dashboard"
        self.refresh_data()
        self.set_interval(5, self.refresh_data)

    @work(exclusive=True, thread=True)
    def refresh_data(self) -> None:
        root = get_project_root()
        
        # Fetch bd status
        summary_data = {}
        try:
            output = subprocess.check_output(
                ["bd", "status", "--json"], 
                cwd=root,
                stderr=subprocess.DEVNULL, 
                text=True,
                timeout=3.0
            )
            status_data = json.loads(output)
            summary_data = status_data.get("summary", {})
        except Exception:
            pass

        # Fetch SCV info
        scvs = get_active_scvs(root)

        self.call_from_thread(self._update_ui, summary_data, scvs)

    def _update_ui(self, summary_data: dict, scvs: dict) -> None:
        # Update mission summary
        summary_widget = self.query_one("#mission-summary", MissionSummary)
        summary_widget.summary_data = summary_data

        # Update SCV table
        table = self.query_one("#scv-table", SCVTable)
        table.clear()
        for objective_id, info in sorted(scvs.items()):
            agent = info.get("agent_name", "unknown")
            pid = str(info.get("pid", "?"))
            model = info.get("model", "unknown")
            duration = format_duration(info.get("start_time"))
            table.add_row(objective_id, agent, pid, model, duration)
        
        # Update status bar with last refresh time
        now = datetime.now().strftime("%H:%M:%S")
        self.sub_title = f"Last Refresh: {now}"

def run_tui():
    app = AdjutantDashboard()
    app.run()
