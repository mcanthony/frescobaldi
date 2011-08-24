# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2011 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
Insert snippets into a Document.
"""

from __future__ import unicode_literals

from PyQt4.QtCore import QSettings
from PyQt4.QtGui import QTextCursor, QMessageBox

import cursortools
import indent
import tokeniter

from . import snippets
from . import expand


def insert(name, view):
    """Insert named snippet into the view."""
    text, variables = snippets.get(name)
    cursor = view.textCursor()
    
    selection = variables.get('selection', '')
    if 'yes' in selection and not cursor.hasSelection():
        return
    if 'strip' in selection:
        cursortools.stripSelection(cursor)
    
    pos = cursor.selectionStart()
    line = cursor.document().findBlock(pos).blockNumber()
    with cursortools.editBlock(cursor):
        
        # insert the snippet, might return a new cursor
        if 'python' in variables:
            new = insert_python(text, cursor)
        else:
            new = insert_snippet(text, cursor, variables)
        
        # QTextBlocks the snippet starts and ends
        block = cursor.document().findBlockByNumber(line)
        last = cursor.block()
        
        # re-indent if not explicitly suppressed by a 'indent: no' variable
        if last != block and 'no' not in variables.get('indent', ''):
            tokeniter.update(block) # tokenize inserted lines
            while True:
                block = block.next()
                if indent.setIndent(block, indent.computeIndent(block)):
                    tokeniter.update(block)
                if block == last:
                    break
    
    if not new and 'keep' in selection:
        end = cursor.position()
        cursor.setPosition(pos)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
    view.setTextCursor(new or cursor)


def insert_snippet(text, cursor, variables):
    """Inserts a normal text snippet.
    
    After the insert, the cursor points to the end of the inserted snippet.
    
    If this function returns a cursor it must be set as the cursor for the view
    after the snippet has been inserted.
    
    """
    exp_base = expand.Expander(cursor)
    
    evs = [] # make a list of events, either text or a constant
    for text, key in snippets.expand(text):
        if text:
            evs.append(text)
        if key == '$':
            evs.append('$')
        elif key:
            # basic variables
            func = getattr(exp_base, key, None)
            if func:
                evs.append(func())
    
    selectionUsed = expand.SELECTION in evs
    # do the padding if 'selection: strip;' is used
    if selectionUsed and 'strip' in variables.get('selection', ''):
        space = '\n' if '\n' in cursor.selection().toPlainText() else ' '
        # change whitespace in previous and next piece of text
        i = evs.index(expand.SELECTION)
        for j in range(i-1, -i, -1):
            if evs[j] not in expand.constants:
                evs[j] = evs[j].rstrip() + space
                break
        for j in range(i+1, len(evs)):
            if evs[j] not in expand.constants:
                evs[j] = space + evs[j].lstrip()
                break
    # now insert the text
    ins = QTextCursor(cursor)
    selectionUsed and ins.setPosition(cursor.selectionStart())
    a, c = -1, -1
    for e in evs:
        if e == expand.ANCHOR:
            a = ins.position()
        elif e == expand.CURSOR:
            c = ins.position()
        elif e == expand.SELECTION:
            ins.setPosition(cursor.selectionEnd())
        else:
            ins.insertText(e)
    cursor.setPosition(ins.position())
    # return a new cursor if requested
    if (a, c) != (-1, -1):
        new = QTextCursor(cursor)
        if a != -1:
            new.setPosition(a)
        if c != -1:
            new.setPosition(c, QTextCursor.KeepAnchor if a != -1 else QTextCursor.MoveAnchor)
        return new


def insert_python(text, cursor):
    """Regards the text as Python code, and exec it.
    
    the following variables are available:
    
    - text: contains selection or '', set it to insert new text

    After the insert, the cursor points to the end of the inserted snippet.
    
    """
    namespace = {
        'cursor': QTextCursor(cursor),
        'state': state(cursor),
        'text': cursor.selection().toPlainText(),
    }
    try:
        code = compile(text, "<snippet>", "exec")
        exec code in namespace
    except Exception:
        import sys, traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.extract_tb(exc_traceback)
        while tb and tb[0][0] != "<snippet>":
            del tb[0]
        msg = ''.join(traceback.format_list(tb) +
                      traceback.format_exception_only(exc_type, exc_value))
        QMessageBox.critical(None, _("Snippet error"), msg)
    else:
        cursor.insertText(namespace['text'])


def state(cursor):
    """Returns the simplestate string for the position of the cursor."""
    import simplestate
    pos = cursor.selectionStart()
    block = cursor.document().findBlock(pos)
    tokens = tokeniter.tokens(block)
    state = tokeniter.state(block)
    column = pos - block.position()
    for t in tokens:
        if t.end > column:
            break
        state.follow(t)
    return simplestate.state(state)

