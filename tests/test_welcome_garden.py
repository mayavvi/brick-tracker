from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WelcomeEditorialTemplateTests(unittest.TestCase):
    def test_welcome_uses_editorial_layout_without_garden_copy(self):
        welcome = (ROOT / "templates" / "welcome.html").read_text(encoding="utf-8")

        self.assertIn("welcome-editorial", welcome)
        self.assertIn("welcome-entry-card", welcome)
        self.assertIn("Project Efficiency &amp; Automation Kernel", welcome)
        self.assertIn("lg:grid-cols-2", welcome)
        self.assertNotIn("cfx-corners", welcome)
        self.assertNotIn("data-cfx", welcome)
        self.assertNotIn("花园", welcome)
        self.assertNotIn("工作花园", welcome)
        self.assertNotIn("WELCOME TO THE WORKBENCH", welcome)
        self.assertNotIn("garden-tag", welcome)

    def test_base_template_is_light_shared_shell_without_cyberfx(self):
        base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")

        self.assertIn("app-shell-header", base)
        self.assertIn("shell-module-menu", base)
        self.assertIn("shell-calendar-panel", base)
        self.assertNotIn("enable_cyberfx", base)
        self.assertNotIn("cyber-fx.js", base)
        self.assertNotIn("CyberFX", base)
        self.assertNotIn("brick-theme", base)
        self.assertNotIn("$store.theme", base)

    def test_light_editorial_css_hooks_exist(self):
        css = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".app-bg", css)
        self.assertIn(".app-shell-header", css)
        self.assertIn(".shell-calendar-panel", css)
        self.assertIn("welcome-editorial", css)
        self.assertIn("welcome-entry-card", css)
        self.assertIn("summary-card", css)


if __name__ == "__main__":
    unittest.main()
