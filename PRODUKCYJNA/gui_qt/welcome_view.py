from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class WelcomeView(QWidget):
    def __init__(self, version_string=""):
        super().__init__()
        self.version_string = version_string
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Spacer top to push main label to center
        layout.addStretch()
        
        label = QLabel("KSeF Invoice Polska")
        label.setAlignment(Qt.AlignCenter)
        
        # Styl: Duża czcionka, półprzezroczysty szary kolor
        label.setStyleSheet("""
            QLabel {
                font-size: 64px;
                font-weight: bold;
                color: rgba(100, 100, 100, 100); 
            }
        """)
        
        layout.addWidget(label)
        
        # Spacer bottom to separate main label from footer
        layout.addStretch()
        
        # Footer
        version_text = f"v{self.version_string}" if self.version_string else "v1.0.0 (Beta)"
        version_label = QLabel(version_text)
        version_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        version_label.setStyleSheet("color: gray; font-size: 12px; margin: 10px;")
        
        layout.addWidget(version_label)
