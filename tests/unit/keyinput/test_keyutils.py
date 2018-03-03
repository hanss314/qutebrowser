# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014-2018 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

import pytest
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget

from tests.unit.keyinput import key_data
from qutebrowser.utils import utils
from qutebrowser.keyinput import keyutils


@pytest.fixture(params=key_data.KEYS, ids=lambda k: k.attribute)
def qt_key(request):
    """Get all existing keys from key_data.py.

    Keys which don't exist with this Qt version result in skipped tests.
    """
    key = request.param
    if key.member is None:
        pytest.skip("Did not find key {}".format(key.attribute))
    return key


@pytest.fixture(params=[key for key in key_data.KEYS if key.qtest],
                ids=lambda k: k.attribute)
def qtest_key(request):
    """Get keys from key_data.py which can be used with QTest."""
    return request.param


def test_key_data():
    """Make sure all possible keys are in key_data.KEYS."""
    key_names = {name[len("Key_"):]
                 for name, value in sorted(vars(Qt).items())
                 if isinstance(value, Qt.Key)}
    key_data_names = {key.attribute for key in sorted(key_data.KEYS)}
    diff = key_names - key_data_names
    assert not diff


class KeyTesterWidget(QWidget):

    """Widget to get the text of QKeyPressEvents.

    This is done so we can check QTest::keyToAscii (qasciikey.cpp) as we can't
    call that directly, only via QTest::keyPress.
    """

    got_text = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = None

    def keyPressEvent(self, e):
        self.text = e.text()
        self.got_text.emit()


class TestKeyInfoText:

    @pytest.mark.parametrize('upper', [False, True])
    def test_text(self, qt_key, upper):
        """Test KeyInfo.text() with all possible keys.

        See key_data.py for inputs and expected values.
        """
        modifiers = Qt.ShiftModifier if upper else Qt.KeyboardModifiers()
        info = keyutils.KeyInfo(qt_key.member, modifiers=modifiers)
        expected = qt_key.uppertext if upper else qt_key.text
        assert info.text() == expected

    @pytest.fixture
    def key_tester(self, qtbot):
        w = KeyTesterWidget()
        qtbot.add_widget(w)
        return w

    def test_text_qtest(self, qtest_key, qtbot, key_tester):
        """Make sure KeyInfo.text() lines up with QTest::keyToAscii.

        See key_data.py for inputs and expected values.
        """
        with qtbot.wait_signal(key_tester.got_text):
            qtbot.keyPress(key_tester, qtest_key.member)

        info = keyutils.KeyInfo(qtest_key.member,
                                modifiers=Qt.KeyboardModifiers())
        assert info.text() == key_tester.text.lower()


class TestKeyToString:

    def test_to_string(self, qt_key):
        assert keyutils._key_to_string(qt_key.member) == qt_key.name

    def test_missing(self, monkeypatch):
        monkeypatch.delattr(keyutils.Qt, 'Key_Blue')
        # We don't want to test the key which is actually missing - we only
        # want to know if the mapping still behaves properly.
        assert keyutils._key_to_string(Qt.Key_A) == 'A'


@pytest.mark.parametrize('key, modifiers, expected', [
    (Qt.Key_A, Qt.NoModifier, 'a'),
    (Qt.Key_A, Qt.ShiftModifier, 'A'),

    (Qt.Key_Tab, Qt.ShiftModifier, '<Shift+Tab>'),
    (Qt.Key_A, Qt.ControlModifier, '<Ctrl+a>'),
    (Qt.Key_A, Qt.ControlModifier | Qt.ShiftModifier, '<Ctrl+Shift+a>'),
    (Qt.Key_A,
     Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier | Qt.ShiftModifier,
     '<Meta+Ctrl+Alt+Shift+a>'),

    (Qt.Key_Shift, Qt.ShiftModifier, '<Shift>'),
    (Qt.Key_Shift, Qt.ShiftModifier | Qt.ControlModifier, '<Ctrl+Shift>'),
])
def test_key_info_str(key, modifiers, expected):
    assert str(keyutils.KeyInfo(key, modifiers)) == expected


@pytest.mark.parametrize('keystr, expected', [
    ('<Control-x>', keyutils.KeySequence(Qt.ControlModifier | Qt.Key_X)),
    ('<Meta-x>', keyutils.KeySequence(Qt.MetaModifier | Qt.Key_X)),
    ('<Ctrl-Alt-y>',
     keyutils.KeySequence(Qt.ControlModifier | Qt.AltModifier | Qt.Key_Y)),
    ('x', keyutils.KeySequence(Qt.Key_X)),
    ('X', keyutils.KeySequence(Qt.ShiftModifier | Qt.Key_X)),
    ('<Escape>', keyutils.KeySequence(Qt.Key_Escape)),
    ('xyz', keyutils.KeySequence(Qt.Key_X, Qt.Key_Y, Qt.Key_Z)),
    ('<Control-x><Meta-y>', keyutils.KeySequence(Qt.ControlModifier | Qt.Key_X,
                                                 Qt.MetaModifier | Qt.Key_Y)),
    ('<blub>', keyutils.KeyParseError),
    ('\U00010000', keyutils.KeyParseError),
])
def test_parse(keystr, expected):
    if expected is keyutils.KeyParseError:
        with pytest.raises(keyutils.KeyParseError):
            keyutils.KeySequence.parse(keystr)
    else:
        assert keyutils.KeySequence.parse(keystr) == expected


@pytest.mark.parametrize('orig, normalized', [
    ('<Control+x>', '<Ctrl+x>'),
    ('<Windows+x>', '<Meta+x>'),
    ('<Mod1+x>', '<Alt+x>'),
    ('<Mod4+x>', '<Meta+x>'),
    ('<Control-->', '<Ctrl+->'),
    ('<Windows++>', '<Meta++>'),
    ('<ctrl-x>', '<Ctrl+x>'),
    ('<control+x>', '<Ctrl+x>')
])
def test_normalize_keystr(orig, normalized):
    assert str(keyutils.KeySequence.parse(orig)) == normalized


@pytest.mark.parametrize('key, printable', [
    (Qt.Key_Control, False),
    (Qt.Key_Escape, False),
    (Qt.Key_Tab, False),
    (Qt.Key_Backtab, False),
    (Qt.Key_Backspace, False),
    (Qt.Key_Return, False),
    (Qt.Key_Enter, False),
    (Qt.Key_X | Qt.ControlModifier, False),  # Wrong usage

    (Qt.Key_Space, True),  # FIXME broken with upper/lower!
    (Qt.Key_ydiaeresis, True),
    (Qt.Key_X, True),
])
def test_is_printable(key, printable):
    assert keyutils.is_printable(key) == printable


@pytest.mark.parametrize('key, ismodifier', [
    (Qt.Key_Control, True),
    (Qt.Key_X, False),
    (Qt.Key_Super_L, False),  # Modifier but not in _MODIFIER_MAP
])
def test_is_modifier_key(key, ismodifier):
    assert keyutils.is_modifier_key(key) == ismodifier
