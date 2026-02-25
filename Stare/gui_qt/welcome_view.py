from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class WelcomeView(QWidget):
    def __init__(self):
        super().__init__()
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
        version_label = QLabel("Wersja KSef 2 FA(3) build 1")
        version_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        version_label.setStyleSheet("color: gray; font-size: 12px; margin: 10px;")
        
        layout.addWidget(version_label)
