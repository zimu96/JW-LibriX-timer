"""
Simple QR code placeholder for network display connections.
"""
from PyQt6.QtGui import QPixmap, QPainter, QFont, QColor, QPen
from PyQt6.QtCore import Qt

def generate_qr_code(url: str, size: int = 200) -> QPixmap:
    """
    Generate a simple placeholder instead of a QR code
    
    Args:
        url: The URL to display
        size: Size of the generated image in pixels
        
    Returns:
        QPixmap containing URL information
    """
    # Create empty pixmap
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.white)
    
    # Draw URL information
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor(0, 0, 0)))
    
    # Draw border
    painter.drawRect(0, 0, size-1, size-1)
    
    # Draw heading
    font = QFont("Arial", 12, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(10, 10, size-20, 30), 
                   Qt.AlignmentFlag.AlignCenter, "Network Display")
    
    # Draw URL
    font = QFont("Arial", 10)
    painter.setFont(font)
    painter.drawText(QRect(10, 50, size-20, size-60), 
                   Qt.AlignmentFlag.AlignCenter, 
                   f"Connect to:\n{url}")
    
    painter.end()
    return pixmap