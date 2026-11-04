"""
Meeting editor dialog for creating and editing meetings in the OnTime Meeting Timer application.
"""
import copy
from datetime import datetime, time
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QTabWidget,
    QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QGroupBox, QFormLayout, QDialogButtonBox, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QDateEdit, QTimeEdit, QMessageBox, QListWidget, QListWidgetItem,
    QStackedWidget, QScrollArea, QFrame, QMenu, QInputDialog
)
from PyQt6.QtCore import Qt, QDate, QTime, pyqtSignal
from PyQt6.QtGui import QAction

from src.models.meeting import Meeting, MeetingSection, MeetingPart, MeetingType, MeetingSource
from src.models.meeting_template import MeetingTemplate, TemplateType


class MeetingEditorDialog(QDialog):
    """Dialog for creating or editing meetings"""
    
    # Signal emitted when a meeting is created/modified
    meeting_updated = pyqtSignal(Meeting)
    
    def __init__(self, parent=None, meeting: Meeting = None, settings_manager=None):
        super().__init__(parent)
        self.meeting = meeting
        self.original_meeting = copy.deepcopy(meeting) if meeting else None
        self.template_manager = MeetingTemplate()
        self.settings_manager = settings_manager
        self.is_new_meeting = meeting is None
        self._target_manually_set = False  # Track if user manually changed target

        # Setup UI
        self._setup_ui()

        # Load meeting data if editing an existing meeting
        if meeting:
            self._load_meeting_data()
        else:
            # Initialize default target based on type
            self._update_target_duration_default()
    
    def _setup_ui(self):
        """Setup the UI components"""
        self.setWindowTitle(self.tr("Meeting Editor"))
        self.resize(800, 600)
        
        main_layout = QVBoxLayout(self)
        
        # Meeting details section
        details_group = QGroupBox(self.tr("Meeting Details"))
        details_layout = QFormLayout(details_group)
        
        # Title
        self.title_edit = QLineEdit()
        details_layout.addRow(self.tr("Title:"), self.title_edit)
        
        # Type
        self.type_combo = QComboBox()
        for meeting_type in MeetingType:
            self.type_combo.addItem(meeting_type.value.capitalize(), meeting_type.value)
        details_layout.addRow("Type:", self.type_combo)
        
        # Connect type change to update template options
        self.type_combo.currentIndexChanged.connect(self._update_template_options)

        # Connect type change to update target duration default
        self.type_combo.currentIndexChanged.connect(self._update_target_duration_default)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        details_layout.addRow(self.tr("Date:"), self.date_edit)
        
        # Time
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("hh:mm AP")
        self.time_edit.setTime(QTime(19, 0))  # Default to 7:00 PM
        details_layout.addRow(self.tr("Time:"), self.time_edit)

        # Target Duration
        target_layout = QHBoxLayout()
        self.target_duration_spin = QSpinBox()
        self.target_duration_spin.setRange(30, 240)  # 30 min to 4 hours
        self.target_duration_spin.setValue(105)  # Default
        self.target_duration_spin.setSuffix(" min")
        self.target_duration_spin.setToolTip(self.tr("Target duration for this meeting"))
        self.target_duration_spin.valueChanged.connect(self._on_target_duration_changed)
        target_layout.addWidget(self.target_duration_spin, 1)

        # Comparison indicator label
        self.target_comparison_label = QLabel()
        self.target_comparison_label.setStyleSheet("font-size: 9pt;")
        target_layout.addWidget(self.target_comparison_label, 1)

        details_layout.addRow(self.tr("Target Duration:"), target_layout)

        # Templates
        template_layout = QHBoxLayout()
        self.template_combo = QComboBox()
        self._populate_template_combo()
        template_layout.addWidget(self.template_combo, 2)

        self.load_template_btn = QPushButton(self.tr("Load Template"))
        self.load_template_btn.clicked.connect(self._load_template)
        template_layout.addWidget(self.load_template_btn, 1)

        details_layout.addRow(self.tr("Template:"), template_layout)

        # Add details group to main layout
        main_layout.addWidget(details_group)
        
        # Meeting structure section
        structure_group = QGroupBox(self.tr("Meeting Structure"))
        structure_layout = QVBoxLayout(structure_group)

        # Total duration display at the top
        duration_header = QHBoxLayout()
        duration_header.addStretch()
        self.total_duration_label = QLabel(self.tr("Total: 0 min"))
        self.total_duration_label.setStyleSheet("font-size: 10pt; color: #666; font-weight: bold;")
        duration_header.addWidget(self.total_duration_label)
        structure_layout.addLayout(duration_header)

        # Split view with sections list on left, parts on right
        split_layout = QHBoxLayout()
        
        # Sections list (left side)
        sections_layout = QVBoxLayout()
        sections_label = QLabel(self.tr("Sections:"))
        sections_layout.addWidget(sections_label)
        
        self.sections_list = QListWidget()
        self.sections_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.sections_list.currentRowChanged.connect(self._section_selected)
        sections_layout.addWidget(self.sections_list)
        
        # Section buttons
        section_buttons_layout = QHBoxLayout()
        self.add_section_btn = QPushButton(self.tr("Add Section"))
        self.add_section_btn.clicked.connect(self._add_section)
        section_buttons_layout.addWidget(self.add_section_btn)
        
        self.edit_section_btn = QPushButton(self.tr("Edit"))
        self.edit_section_btn.clicked.connect(self._edit_section)
        section_buttons_layout.addWidget(self.edit_section_btn)

        self.remove_section_btn = QPushButton(self.tr("Remove"))
        self.remove_section_btn.clicked.connect(self._remove_section)
        section_buttons_layout.addWidget(self.remove_section_btn)
        
        sections_layout.addLayout(section_buttons_layout)
        split_layout.addLayout(sections_layout, 1)
        
        # Parts table (right side)
        parts_layout = QVBoxLayout()

        self.current_section_label = QLabel(self.tr("No section selected"))
        parts_layout.addWidget(self.current_section_label)
        
        self.parts_table = QTableWidget(0, 3)  # 0 rows, 3 columns (Title, Duration, Presenter)
        self.parts_table.setHorizontalHeaderLabels([self.tr("Title"), self.tr("Minutes"), self.tr("Presenter")])
        self.parts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.parts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.parts_table.setColumnWidth(1, 80)
        self.parts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.parts_table.setColumnWidth(2, 150)
        self.parts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.parts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.parts_table.customContextMenuRequested.connect(self._show_part_context_menu)
        parts_layout.addWidget(self.parts_table)
        
        # Part buttons
        part_buttons_layout = QHBoxLayout()
        self.add_part_btn = QPushButton(self.tr("Add Part"))
        self.add_part_btn.clicked.connect(self._add_part)
        part_buttons_layout.addWidget(self.add_part_btn)

        self.edit_part_btn = QPushButton(self.tr("Edit Part"))
        self.edit_part_btn.clicked.connect(self._edit_part)
        part_buttons_layout.addWidget(self.edit_part_btn)

        self.remove_part_btn = QPushButton(self.tr("Remove Part"))
        self.remove_part_btn.clicked.connect(self._remove_part)
        part_buttons_layout.addWidget(self.remove_part_btn)
        
        parts_layout.addLayout(part_buttons_layout)
        split_layout.addLayout(parts_layout, 2)
        
        structure_layout.addLayout(split_layout)
        main_layout.addWidget(structure_group, 2)  # Give structure section more space
        
        # Buttons at bottom
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Add save as template button
        self.save_template_btn = QPushButton(self.tr("Save as Template"))
        self.save_template_btn.clicked.connect(self._save_as_template)
        button_box.addButton(self.save_template_btn, QDialogButtonBox.ButtonRole.ActionRole)
        
        main_layout.addWidget(button_box)
        
        # Initialize UI state
        self._update_controls_state()
    
    def _populate_template_combo(self):
        """Populate template combo box based on selected meeting type"""
        self.template_combo.clear()
        
        if self.type_combo.currentData() == MeetingType.MIDWEEK.value:
            self.template_combo.addItem(self.tr("Default Midweek Template"), TemplateType.MIDWEEK.value)
        elif self.type_combo.currentData() == MeetingType.WEEKEND.value:
            self.template_combo.addItem(self.tr("Default Weekend Template"), TemplateType.WEEKEND.value)
        else:
            self.template_combo.addItem(self.tr("Default Custom Template"), TemplateType.CUSTOM.value)

        # TODO: Add user-defined templates here
        
        # Add blank option
        self.template_combo.addItem(self.tr("Start Blank"), "blank")

    def _update_template_options(self):
        """Update template options when meeting type changes"""
        self._populate_template_combo()
    
    def _load_template(self):
        """Load the selected template into the editor"""
        template_type_str = self.template_combo.currentData()
        
        if template_type_str == "blank":
            # Clear all sections and parts
            self.sections_list.clear()
            self.parts_table.setRowCount(0)
            self.current_section_label.setText(self.tr("No section selected"))
            return
        
        # Convert string to template type enum
        if template_type_str == TemplateType.MIDWEEK.value:
            template_type = TemplateType.MIDWEEK
        elif template_type_str == TemplateType.WEEKEND.value:
            template_type = TemplateType.WEEKEND
        else:
            template_type = TemplateType.CUSTOM
        
        # Get template data
        template_data = self.template_manager.get_template(template_type)
        
        # Clear existing sections
        self.sections_list.clear()
        
        # Add sections from template
        for section_data in template_data.get('sections', []):
            section_title = section_data.get('title', '')
            self._add_section_item(section_title, section_data.get('parts', []))

        # Select first section if any
        if self.sections_list.count() > 0:
            self.sections_list.setCurrentRow(0)

        # Auto-calculate target from template
        if self.sections_list.count() > 0:
            total = self._calculate_total_duration()
            # Round up to nearest 5 minutes
            suggested_target = ((total + 4) // 5) * 5
            self.target_duration_spin.setValue(suggested_target)
            self._update_duration_comparison()
    
    def _add_section_item(self, title: str, parts=None):
        """Add a section item to the sections list"""
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, parts or [])
        self.sections_list.addItem(item)
        return item
    
    def _section_selected(self, index):
        """Handle section selection change"""
        # Clear the part selection to prevent stale selections
        self.parts_table.clearSelection()
        
        if index < 0:
            self.current_section_label.setText(self.tr("No section selected"))
            self.parts_table.setRowCount(0)
            self._update_controls_state()
            return
        
        # Get selected section
        item = self.sections_list.item(index)
        section_title = item.text()
        self.current_section_label.setText(self.tr(f"Parts in section: {section_title}"))

        # Get parts for this section
        parts_data = item.data(Qt.ItemDataRole.UserRole)
        
        # Disconnect selection changed signal temporarily to avoid multiple calls
        if hasattr(self, '_selection_connected') and self._selection_connected:
            try:
                self.parts_table.itemSelectionChanged.disconnect(self._update_controls_state)
                self._selection_connected = False
            except TypeError:
                # Signal was not connected
                pass
        
        # Populate parts table
        self.parts_table.setRowCount(len(parts_data))
        
        for i, part in enumerate(parts_data):
            # Title
            title_item = QTableWidgetItem(part.get('title', ''))
            self.parts_table.setItem(i, 0, title_item)
            
            # Duration
            duration_item = QTableWidgetItem(str(part.get('duration_minutes', 0)))
            self.parts_table.setItem(i, 1, duration_item)
            
            # Presenter
            presenter_item = QTableWidgetItem(part.get('presenter', ''))
            self.parts_table.setItem(i, 2, presenter_item)
        
        # Reconnect selection changed signal
        self.parts_table.itemSelectionChanged.connect(self._update_controls_state)
        self._selection_connected = True

        self._update_controls_state()
        self._update_duration_comparison()

    def _add_section(self):
        """Add a new section"""
        section_title, ok = QInputDialog.getText(self, self.tr("Add Section"), self.tr("Section Title:"))
        if ok and section_title:
            self._add_section_item(section_title)
            # Select the newly added section
            self.sections_list.setCurrentRow(self.sections_list.count() - 1)
    
    def _edit_section(self):
        """Edit selected section"""
        current_row = self.sections_list.currentRow()
        if current_row < 0:
            return
        
        item = self.sections_list.item(current_row)
        old_title = item.text()

        new_title, ok = QInputDialog.getText(self, self.tr("Edit Section"), self.tr("Section Title:"), text=old_title)
        if ok and new_title:
            item.setText(new_title)
    
    def _remove_section(self):
        """Remove selected section"""
        current_row = self.sections_list.currentRow()
        if current_row < 0:
            return
        
        reply = QMessageBox.question(
            self, self.tr("Confirm Removal"),
            self.tr("Remove this section and all its parts?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.sections_list.takeItem(current_row)
    
    def _add_part(self):
        """Add a new part to the current section"""
        current_row = self.sections_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, self.tr("No Section Selected"), self.tr("Please select a section first."))
            return
        
        # Simple dialog for part details
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Add Part"))
        dialog_layout = QFormLayout(dialog)
        
        title_edit = QLineEdit()
        dialog_layout.addRow(self.tr("Title:"), title_edit)

        duration_spin = QSpinBox()
        duration_spin.setMinimum(1)
        duration_spin.setMaximum(120)
        duration_spin.setValue(5)
        dialog_layout.addRow(self.tr("Duration (minutes):"), duration_spin)
        
        presenter_edit = QLineEdit()
        dialog_layout.addRow(self.tr("Presenter:"), presenter_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        dialog_layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            part_title = title_edit.text()
            duration = duration_spin.value()
            presenter = presenter_edit.text()
            
            if not part_title:
                return
            
            # Add new part to the table
            row_count = self.parts_table.rowCount()
            self.parts_table.setRowCount(row_count + 1)
            
            self.parts_table.setItem(row_count, 0, QTableWidgetItem(part_title))
            self.parts_table.setItem(row_count, 1, QTableWidgetItem(str(duration)))
            self.parts_table.setItem(row_count, 2, QTableWidgetItem(presenter))
            
            # Update section's parts data
            self._update_section_parts_data()
    
    def _edit_part(self):
        """Edit selected part"""
        selected_rows = self.parts_table.selectedItems()
        if not selected_rows:
            return
        
        # Get the row of the first selected item
        selected_row = selected_rows[0].row()
        
        # Make sure all selected items are in the same row
        same_row = all(item.row() == selected_row for item in selected_rows)
        if not same_row:
            # Select only the first row
            self.parts_table.setRangeSelected(
                self.parts_table.selectedRanges()[0], False)
            self.parts_table.selectRow(selected_row)
        
        # Get current part data
        title_item = self.parts_table.item(selected_row, 0)
        duration_item = self.parts_table.item(selected_row, 1)
        presenter_item = self.parts_table.item(selected_row, 2)
        
        if not title_item or not duration_item:
            return
        
        # Simple dialog for part details
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Edit Part"))
        dialog_layout = QFormLayout(dialog)
        
        title_edit = QLineEdit(title_item.text())
        dialog_layout.addRow(self.tr("Title:"), title_edit)

        duration_spin = QSpinBox()
        duration_spin.setMinimum(1)
        duration_spin.setMaximum(120)
        try:
            duration_spin.setValue(int(duration_item.text()))
        except (ValueError, TypeError):
            duration_spin.setValue(5)
        dialog_layout.addRow(self.tr("Duration (minutes):"), duration_spin)

        presenter_edit = QLineEdit(presenter_item.text() if presenter_item else "")
        dialog_layout.addRow(self.tr("Presenter:"), presenter_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        dialog_layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            part_title = title_edit.text()
            duration = duration_spin.value()
            presenter = presenter_edit.text()
            
            if not part_title:
                return
            
            # Update part data
            self.parts_table.setItem(selected_row, 0, QTableWidgetItem(part_title))
            self.parts_table.setItem(selected_row, 1, QTableWidgetItem(str(duration)))
            self.parts_table.setItem(selected_row, 2, QTableWidgetItem(presenter))
            
            # Update section's parts data
            self._update_section_parts_data()
    
    def _remove_part(self):
        """Remove selected part"""
        selected_items = self.parts_table.selectedItems()
        if not selected_items:
            return
        
        # Get the row of the first selected item
        selected_row = selected_items[0].row()
        
        reply = QMessageBox.question(
            self, self.tr("Confirm Removal"),
            self.tr("Remove this part?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.parts_table.removeRow(selected_row)
            
            # Update section's parts data
            self._update_section_parts_data()
    
    def _show_part_context_menu(self, position):
        """Show context menu for parts table"""
        selected_items = self.parts_table.selectedItems()
        if not selected_items:
            return
        
        # Create context menu
        menu = QMenu(self)

        edit_action = QAction(self.tr("Edit Part"), self)
        edit_action.triggered.connect(self._edit_part)
        menu.addAction(edit_action)

        remove_action = QAction(self.tr("Remove Part"), self)
        remove_action.triggered.connect(self._remove_part)
        menu.addAction(remove_action)
        
        # Add move up/down actions
        move_up_action = QAction(self.tr("Move Up"), self)
        move_up_action.triggered.connect(self._move_part_up)
        menu.addAction(move_up_action)

        move_down_action = QAction(self.tr("Move Down"), self)
        move_down_action.triggered.connect(self._move_part_down)
        menu.addAction(move_down_action)
        
        # Show the menu
        menu.exec(self.parts_table.mapToGlobal(position))
    
    def _move_part_up(self):
        """Move selected part up in the list"""
        selected_items = self.parts_table.selectedItems()
        if not selected_items:
            return
        
        # Get the row of the first selected item
        selected_row = selected_items[0].row()
        
        # Check if we can move up
        if selected_row <= 0:
            return
        
        # Get data from both rows
        current_row_data = []
        above_row_data = []
        
        for col in range(self.parts_table.columnCount()):
            current_item = self.parts_table.item(selected_row, col)
            above_item = self.parts_table.item(selected_row - 1, col)
            
            if current_item and above_item:
                current_row_data.append(current_item.text())
                above_row_data.append(above_item.text())
            else:
                current_row_data.append("")
                above_row_data.append("")
        
        # Swap the data
        for col in range(self.parts_table.columnCount()):
            self.parts_table.setItem(selected_row - 1, col, QTableWidgetItem(current_row_data[col]))
            self.parts_table.setItem(selected_row, col, QTableWidgetItem(above_row_data[col]))
        
        # Update selection
        self.parts_table.clearSelection()
        self.parts_table.selectRow(selected_row - 1)
        
        # Update section's parts data
        self._update_section_parts_data()
    
    def _move_part_down(self):
        """Move selected part down in the list"""
        selected_items = self.parts_table.selectedItems()
        if not selected_items:
            return
        
        # Get the row of the first selected item
        selected_row = selected_items[0].row()
        
        # Check if we can move down
        if selected_row >= self.parts_table.rowCount() - 1:
            return
        
        # Get data from both rows
        current_row_data = []
        below_row_data = []
        
        for col in range(self.parts_table.columnCount()):
            current_item = self.parts_table.item(selected_row, col)
            below_item = self.parts_table.item(selected_row + 1, col)
            
            if current_item and below_item:
                current_row_data.append(current_item.text())
                below_row_data.append(below_item.text())
            else:
                current_row_data.append("")
                below_row_data.append("")
        
        # Swap the data
        for col in range(self.parts_table.columnCount()):
            self.parts_table.setItem(selected_row + 1, col, QTableWidgetItem(current_row_data[col]))
            self.parts_table.setItem(selected_row, col, QTableWidgetItem(below_row_data[col]))
        
        # Update selection
        self.parts_table.clearSelection()
        self.parts_table.selectRow(selected_row + 1)
        
        # Update section's parts data
        self._update_section_parts_data()
    
    def _update_section_parts_data(self):
        """Update the selected section's parts data from the table"""
        current_row = self.sections_list.currentRow()
        if current_row < 0:
            return
        
        item = self.sections_list.item(current_row)
        parts_data = []
        
        for row in range(self.parts_table.rowCount()):
            title_item = self.parts_table.item(row, 0)
            duration_item = self.parts_table.item(row, 1)
            presenter_item = self.parts_table.item(row, 2)
            
            if title_item and duration_item:
                try:
                    duration = int(duration_item.text())
                except (ValueError, TypeError):
                    duration = 0
                
                part_data = {
                    'title': title_item.text(),
                    'duration_minutes': duration,
                    'presenter': presenter_item.text() if presenter_item else "",
                    'notes': ""  # Default empty notes
                }
                parts_data.append(part_data)
        
        item.setData(Qt.ItemDataRole.UserRole, parts_data)
        self._update_duration_comparison()

    def _calculate_total_duration(self) -> int:
        """Calculate total duration of all parts in all sections"""
        total_minutes = 0
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            parts_data = item.data(Qt.ItemDataRole.UserRole)
            if parts_data:
                for part in parts_data:
                    total_minutes += part.get('duration_minutes', 0)
        return total_minutes

    def _update_duration_comparison(self):
        """Update total duration display and comparison indicator"""
        total = self._calculate_total_duration()
        target = self.target_duration_spin.value()

        # Update total label
        self.total_duration_label.setText(self.tr(f"Total: {total} min"))

        if total == 0:
            self.target_comparison_label.setText("")
            return

        diff = target - total

        if diff > 5:
            # Under target (good)
            self.target_comparison_label.setText(f"✓ {diff} min under")
            self.target_comparison_label.setStyleSheet("color: #4CAF50; font-size: 9pt;")
        elif diff >= 0:
            # Near target (acceptable)
            self.target_comparison_label.setText(f"≈ Near target")
            self.target_comparison_label.setStyleSheet("color: #FF9800; font-size: 9pt;")
        else:
            # Over target (warning)
            self.target_comparison_label.setText(f"⚠ {abs(diff)} min over")
            self.target_comparison_label.setStyleSheet("color: #F44336; font-size: 9pt;")

    def _update_target_duration_default(self):
        """Update target duration default when meeting type changes"""
        if not hasattr(self, '_target_manually_set') or not self._target_manually_set:
            meeting_type_str = self.type_combo.currentData()
            settings = None
            parent = self.parent()

            if parent and hasattr(parent, 'settings_controller'):
                settings = parent.settings_controller.get_settings()

            if settings:
                if meeting_type_str == MeetingType.MIDWEEK.value:
                    self.target_duration_spin.setValue(settings.midweek_meeting.target_duration_minutes)
                elif meeting_type_str == MeetingType.WEEKEND.value:
                    self.target_duration_spin.setValue(settings.weekend_meeting.target_duration_minutes)
                else:  # CUSTOM
                    self.target_duration_spin.setValue(60)
            else:
                self.target_duration_spin.setValue(105)

        self._update_duration_comparison()

    def _on_target_duration_changed(self, value):
        """Track manual edits to target duration"""
        self._target_manually_set = True
        self._update_duration_comparison()

    def _save_as_template(self):
        """Save current meeting as a template"""
        # Create template from current meeting structure
        template_data = {
            'title': self.title_edit.text(),
            'language': 'en',  # Default
            'sections': []
        }
        
        # Add sections and parts
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            section_data = {
                'title': item.text(),
                'parts': item.data(Qt.ItemDataRole.UserRole)
            }
            template_data['sections'].append(section_data)
        
        # Determine template type
        meeting_type = self.type_combo.currentData()
        if meeting_type == MeetingType.MIDWEEK.value:
            template_type = TemplateType.MIDWEEK
        elif meeting_type == MeetingType.WEEKEND.value:
            template_type = TemplateType.WEEKEND
        else:
            template_type = TemplateType.CUSTOM
        
        # Save template
        success = self.template_manager.save_template(template_type, template_data)
        
        if success:
            QMessageBox.information(self, self.tr("Template Saved"),
                                   self.tr(f"Template saved as {template_type.value} template."))
        else:
            QMessageBox.warning(self, self.tr("Save Failed"),
                               self.tr("Failed to save template. Please check permissions."))

    def _update_controls_state(self):
        """Update enabled/disabled state of controls"""
        has_section = self.sections_list.currentRow() >= 0
        
        # Section controls
        self.edit_section_btn.setEnabled(has_section)
        self.remove_section_btn.setEnabled(has_section)
        
        # Part controls
        self.add_part_btn.setEnabled(has_section)
        
        # Check if there are any selected items in the parts table
        has_part = bool(self.parts_table.selectedItems())  # Convert to boolean
        self.edit_part_btn.setEnabled(has_part)
        self.remove_part_btn.setEnabled(has_part)
        
        # Connect selection changed signal if not already connected
        if not hasattr(self, '_selection_connected'):
            self.parts_table.itemSelectionChanged.connect(self._update_controls_state)
            self._selection_connected = True
    
    def _load_meeting_data(self):
        """Load meeting data into the UI when editing an existing meeting"""
        if not self.meeting:
            return
        
        # Set meeting details
        self.title_edit.setText(self.meeting.title)
        
        type_index = self.type_combo.findData(self.meeting.meeting_type.value)
        if type_index >= 0:
            self.type_combo.setCurrentIndex(type_index)
        
        self.date_edit.setDate(QDate(
            self.meeting.date.year,
            self.meeting.date.month,
            self.meeting.date.day
        ))
        
        self.time_edit.setTime(QTime(
            self.meeting.start_time.hour,
            self.meeting.start_time.minute
        ))
        
        # Populate sections and parts
        self.sections_list.clear()
        
        for section in self.meeting.sections:
            # Convert parts to dict format for consistency
            parts_data = []
            for part in section.parts:
                part_data = {
                    'title': part.title,
                    'duration_minutes': part.duration_minutes,
                    'presenter': part.presenter,
                    'notes': part.notes
                }
                parts_data.append(part_data)
            
            self._add_section_item(section.title, parts_data)

        # Select first section if any
        if self.sections_list.count() > 0:
            self.sections_list.setCurrentRow(0)

        # Load target duration if set
        if self.meeting.target_duration_minutes is not None:
            self.target_duration_spin.setValue(self.meeting.target_duration_minutes)
        else:
            self._update_target_duration_default()

        self._update_duration_comparison()

    def create_meeting(self) -> Meeting:
        """Create a Meeting object from the editor data"""
        # Get meeting basics
        meeting_type_str = self.type_combo.currentData()
        if meeting_type_str == MeetingType.MIDWEEK.value:
            meeting_type = MeetingType.MIDWEEK
        elif meeting_type_str == MeetingType.WEEKEND.value:
            meeting_type = MeetingType.WEEKEND
        else:
            meeting_type = MeetingType.CUSTOM
        
        title = self.title_edit.text()
        
        # Get date and time
        qdate = self.date_edit.date()
        qtime = self.time_edit.time()
        
        meeting_date = datetime(
            qdate.year(),
            qdate.month(),
            qdate.day()
        )
        
        meeting_time = time(
            qtime.hour(),
            qtime.minute()
        )
        
        # Create sections
        sections = []
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            section_title = item.text()
            parts_data = item.data(Qt.ItemDataRole.UserRole)
            
            # Create parts
            parts = []
            for part_data in parts_data:
                part = MeetingPart(
                    title=part_data.get('title', ''),
                    duration_minutes=part_data.get('duration_minutes', 0),
                    presenter=part_data.get('presenter', ''),
                    notes=part_data.get('notes', '')
                )
                parts.append(part)
            
            section = MeetingSection(
                title=section_title,
                parts=parts
            )
            sections.append(section)
        
        # Create meeting - tag as manually created so it doesn't override scraped data
        meeting = Meeting(
            meeting_type=meeting_type,
            title=title,
            date=meeting_date,
            start_time=meeting_time,
            sections=sections,
            language='en',  # Default
            target_duration_minutes=self.target_duration_spin.value(),
            source=MeetingSource.MANUAL
        )

        return meeting
    
    def accept(self):
        """Handle dialog acceptance"""
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, self.tr("Missing Data"), self.tr("Please enter a meeting title."))
            return

        if len(title) < 3:
            QMessageBox.warning(
                self, self.tr("Invalid Title"),
                self.tr("Meeting title must be at least 3 characters long.")
            )
            return
        
        if self.sections_list.count() == 0:
            QMessageBox.warning(self, self.tr("Missing Data"), self.tr("Please add at least one section."))
            return
        
        # Check if any section has no parts
        for i in range(self.sections_list.count()):
            item = self.sections_list.item(i)
            parts_data = item.data(Qt.ItemDataRole.UserRole)
            if not parts_data:
                QMessageBox.warning(
                    self, self.tr("Missing Data"),
                    self.tr(f"Section '{item.text()}' has no parts. Please add at least one part.")
                )
                return
        
        # Create meeting from UI data
        meeting = self.create_meeting()
        
        # Emit signal with new meeting
        self.meeting_updated.emit(meeting)
        
        super().accept()