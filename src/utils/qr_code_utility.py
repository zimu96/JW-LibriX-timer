"""
QR code generation utility for network display connections.
"""
import qrcode
from io import BytesIO
from PyQt6.QtGui import QPixmap, QImage


def generate_qr_code(url: str, size: int = 200) -> QPixmap:
    """
    Generate a QR code for the given URL
    
    Args:
        url: The URL to encode in the QR code
        size: Size of the generated QR code in pixels
        
    Returns:
        QPixmap containing the QR code image
    """
    try:
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create PIL image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert PIL image to QPixmap
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        qimage = QImage.fromData(buffer.read())
        pixmap = QPixmap.fromImage(qimage)
        
        # Scale to desired size
        pixmap = pixmap.scaled(size, size)
        
        return pixmap
    
    except Exception as e:
        # If qrcode module is not available or fails, create a placeholder
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPainter, QFont, QPen, QColor
        
        # Create empty pixmap
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.white)
        
        # Draw error message
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(0, 0, 0)))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, 
                        f"QR Error:\n{str(e)}\n\nURL: {url}")
        painter.end()
        
        return pixmap