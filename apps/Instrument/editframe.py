import wx
import sys
import time

import epics
from epics.wx import EpicsFunction

from epicscollect.gui import  empty_bitmap, add_button, add_menu, \
     Closure, NumericCombo, pack, popup, SimpleText, \
     FileSave, FileOpen, SelectWorkdir 

from utils import GUIColors, HideShow, YesNo, set_font_with_children, guess_pvtype

class pvNameCtrl(wx.TextCtrl):
    def __init__(self, owner, panel,  value='', **kws):
        self.owner = owner
        wx.TextCtrl.__init__(self, panel, wx.ID_ANY, value='', **kws)
        self.Bind(wx.EVT_CHAR, self.onChar)
        self.Bind(wx.EVT_KILL_FOCUS, self.onFocus)

    def onFocus(self, evt=None):
        self.owner.connect_pv(self.Value, wid=self.GetId())
        evt.Skip()

    def onChar(self, event):
        key   = event.GetKeyCode()
        entry = wx.TextCtrl.GetValue(self).strip()
        pos   = wx.TextCtrl.GetSelection(self)
        if (key == wx.WXK_RETURN):
            self.owner.connect_pv(entry, wid=self.GetId())
        event.Skip()

class FocusEventFrame(wx.Window):
    """mixin for Frames that all EVT_KILL_FOCUS/EVT_SET_FOCUS events"""
    def Handle_FocusEvents(self, closeEventHandler=None):
        self._closeHandler = closeEventHandler
        self.Bind(wx.EVT_CLOSE, self.closeFrame)
        
    def closeFrame(self, event):
        win = wx.Window_FindFocus()
        if win is not None:
            win.Disconnect(-1, -1, wx.wxEVT_KILL_FOCUS)
        if self._closeHandler is not None:
            self._closeHandler(event)
        else:
            event.Skip()
            
class EditInstrumentFrame(wx.Frame, FocusEventFrame) :
    """ Edit / Add Instrument"""
    def __init__(self, parent=None, pos=(-1, -1), inst=None, db=None):

        self.pvs = {}
        title = 'Add New Instrument'
        if inst is not None:
            title = 'Edit Instrument  %s ' % inst.name

        style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL
        wx.Frame.__init__(self, None, -1, title,  size=(550, -1),
                          style=style, pos=pos)
        self.Handle_FocusEvents()
        
        panel = wx.Panel(self, style=wx.GROW)
        self.colors = GUIColors()

        font = self.GetFont()
        if parent is not None:
            font = parent.GetFont()
            
        titlefont  = font
        titlefont.PointSize += 1
        titlefont.SetWeight(wx.BOLD)
        
        panel.SetBackgroundColour(self.colors.bg)

        self.parent = parent
        self.db = db
        self.inst = db.get_instrument(inst)
        self.connecting_pvs = {}

        STY  = wx.GROW|wx.ALL|wx.ALIGN_CENTER_VERTICAL
        LSTY = wx.ALIGN_LEFT|wx.GROW|wx.ALL|wx.ALIGN_CENTER_VERTICAL
        RSTY = wx.ALIGN_RIGHT|STY
        CSTY = wx.ALIGN_CENTER|STY
        CEN  = wx.ALIGN_CENTER|wx.GROW|wx.ALL
        LEFT = wx.ALIGN_LEFT|wx.GROW|wx.ALL

        self.etimer = wx.Timer(self)
        self.etimer_count = 0
        self.Bind(wx.EVT_TIMER, self.onTimer, self.etimer)

        sizer = wx.GridBagSizer(12, 3)

        # Name row
        label  = SimpleText(panel, 'Instrument Name: ',
                            minsize=(150, -1), style=LSTY)
        self.name =  wx.TextCtrl(panel, value='', size=(250, -1))

        btn_remove = add_button(panel, 'Remove', size=(85, -1),
                                action=self.onRemoveInst)
        sizer.Add(label,      (0, 0), (1, 1), LSTY, 2)
        sizer.Add(self.name,  (0, 1), (1, 1), LSTY, 2)
        sizer.Add(btn_remove, (0, 2), (1, 1), RSTY, 2)
        sizer.Add(wx.StaticLine(panel, size=(195, -1), style=wx.LI_HORIZONTAL),
                  (1, 0), (1, 3), CEN, 2)

        irow = 2
        self.delete_pvs = {}
        if inst is not None:
            self.name.SetValue(inst.name)
            sizer.Add(SimpleText(panel, 'Current PVs:', font=titlefont,
                                 colour=self.colors.title, style=LSTY),
                      (2, 0), (1, 1), LSTY, 2)
            sizer.Add(SimpleText(panel, 'Display Type:',
                                 colour=self.colors.title, style=CSTY),
                      (2, 1), (1, 1), LSTY, 2)
            sizer.Add(SimpleText(panel, 'Remove?:',
                                 colour=self.colors.title, style=CSTY),
                      (2, 2), (1, 1), RSTY, 2)
                
            for pv in inst.pvs:
                irow += 1
                label= SimpleText(panel, pv.name,  minsize=(175, -1),
                                  style=LSTY)
                pvtype = SimpleText(panel, pv.pvtype.name,  minsize=(120, -1),
                                   style=LSTY)
                del_pv = YesNo(panel, defaultyes=False)
                self.delete_pvs[pv.name] = del_pv

                sizer.Add(label,     (irow, 0), (1, 1), LSTY,  3)
                sizer.Add(pvtype,    (irow, 1), (1, 1), CSTY,  3)
                sizer.Add(del_pv,    (irow, 2), (1, 1), RSTY,  3)
 
            irow += 1
            sizer.Add(wx.StaticLine(panel, size=(150, -1),
                                    style=wx.LI_HORIZONTAL),
                      (irow, 0), (1, 3), CEN, 0)
            irow += 1

            
        txt =SimpleText(panel, 'New PVs:', font=titlefont,
                        colour=self.colors.title, style=LSTY)
        
        sizer.Add(txt, (irow, 0), (1, 1), LEFT, 3)
        sizer.Add(SimpleText(panel, 'Display Type',
                             colour=self.colors.title, style=CSTY),
                  (irow, 1), (1, 1), LSTY, 2)
        sizer.Add(SimpleText(panel, 'Remove?',
                             colour=self.colors.title, style=CSTY),
                  (irow, 2), (1, 1), RSTY, 2)


        self.newpvs = {}
        for newpvs in range(5):
            irow += 1
            name = pvNameCtrl(self, panel, value='', size=(175, -1))
            status = SimpleText(panel, 'not connected',  minsize=(120, -1),
                                style=LSTY)
            del_pv = YesNo(panel, defaultyes=False)
            del_pv.Disable()
            sizer.Add(name,     (irow, 0), (1, 1), LSTY,  3)
            sizer.Add(status,   (irow, 1), (1, 1), CSTY,  3)
            sizer.Add(del_pv,   (irow, 2), (1, 1), RSTY,  3)
                        
            self.newpvs[name.GetId()] = [status, del_pv]

        btn_panel = wx.Panel(panel, size=(75, -1))
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_ok     = add_button(btn_panel, 'OK',     size=(70, -1), action=self.onOK)
        btn_cancel = add_button(btn_panel, 'Cancel', size=(70, -1), action=self.onCancel)
                            
        btn_sizer.Add(btn_ok,     0, wx.ALIGN_LEFT,  2)
        btn_sizer.Add(btn_cancel, 0, wx.ALIGN_RIGHT,  2)
        pack(btn_panel, btn_sizer)
        
        irow += 1
        sizer.Add(wx.StaticLine(panel, size=(150, -1), style=wx.LI_HORIZONTAL),
                  (irow, 0), (1, 3), CEN, 2)
        sizer.Add(btn_panel, (irow+1, 1), (1, 2), CEN, 2)
        sizer.Add(wx.StaticLine(panel, size=(150, -1), style=wx.LI_HORIZONTAL),
                  (irow+2, 0), (1, 3), CEN, 2)

        pack(panel, sizer)

        mainsizer = wx.BoxSizer(wx.VERTICAL)
        mainsizer.Add(panel, 1, LSTY)
        pack(self, mainsizer)

        set_font_with_children(self, font)

        self.Layout()
        self.Show()
        self.Raise()

    def get_page_map(self):
        out = {}
        for i in range(self.parent.nb.GetPageCount()):
            out[self.parent.nb.GetPageText(i)] = i
        return out
        
            
    @EpicsFunction
    def connect_pv(self, pvname, wid=None):
        if pvname is None or len(pvname) < 1:
            return

        print 'Connect PV: ', pvname, wid, self.connecting_pvs
        if pvname not in self.connecting_pvs:
            if pvname not in self.pvs:
                print 'connect PV2: ', type(pvname), pvname
                self.pvs[pvname] = epics.PV(pvname)
            self.connecting_pvs[pvname] = wid
            
            if not self.etimer.IsRunning():
                self.etimer.Start(500)
                
    def onTimer(self, event=None):
        if len(self.connecting_pvs) == 0:
            self.etimer.Stop()
        for pvname in self.connecting_pvs:
            self.new_pv_connected(pvname)

    @EpicsFunction
    def new_pv_connected(self, pvname):
        if pvname not in self.pvs:
            pv = self.pvs[pvname] = epics.PV(pvname)
        else:
            pv = self.pvs[pvname]
        # return if not connected
        if pv.connected == False:
            return
        try:
            wid = self.connecting_pvs.pop(pvname)
        except KeyError:
            wid = None
        pv.get_ctrlvars()
        print 'new connected PV ', pv, wid
        self.newpvs[wid][0].SetLabel('Connected!')
        self.newpvs[wid][1].Show()
        self.newpvs[wid][1].Raise()
        self.newpvs[wid][1].Enable()
        self.delete_pvs[pvname] = self.newpvs[wid][1]
        print self.newpvs[wid][1]
        pref = pvname
        if '.' in pvname:
            pref, suff = pvname.split('.')
        desc  = epics.caget("%s.DESC" % pref)
        rectype = epics.caget("%s.RTYP" % pref)
        devtype = pv.type
        pvtype = guess_pvtype(devtype, rectype)
        
        self.newpvs[wid][0].SetLabel(dtype)
        pvtype 
        instpanel = self.parent.nb.GetCurrentPage()
        inst = instpanel.inst
        db = instpanel.db
        print 'self.parent.inst: ', inst, inst.pvs
        db.add_pv(pvname, pvtype=pvtype)
        # db.commit()
        isnt.pvs.append(db.get_pv(pvname))
        db.commit()        
        self.parent.add_pv(pv)
        
    def onRemoveInst(self, event=None):
        print 'Remove Instrument -- verify'
        
    def onOK(self, event=None):
        print 'onOK'
                
    def onCancel(self, event=None):
        self.Destroy()

