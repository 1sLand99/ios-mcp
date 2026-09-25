// Test setup only: rotate the real UI, never intercept OCR/capture/HID methods.
function main(fn) {
  return new Promise((ok, bad) => ObjC.schedule(ObjC.mainQueue, () => {
    try { ok(fn()); } catch (e) { bad(String(e)); }
  }));
}
rpc.exports = {
  state() { return main(() => ({
    orientation: Number(ObjC.classes.UIApplication.sharedApplication().statusBarOrientation()),
    locked: Boolean(ObjC.classes.SBOrientationLockManager.sharedInstance().isUserLocked())
  })); },
  lock(value) { return main(() => {
    const manager = ObjC.classes.SBOrientationLockManager.sharedInstance();
    if (value) manager.lock(); else manager.unlock();
  }); },
  rotate(value) { return main(() => {
    ObjC.classes.UIApplication.sharedApplication()['- _setDeviceOrientation:animated:logMessage:'](
      value, true, ObjC.classes.NSString.stringWithString_('ios-mcp OCR regression'));
  }); },
  // iOS 16+ app-scene rotation, for iPads where the legacy SpringBoard helper
  // no longer moves the foreground scene. This is test setup, not OCR code.
  // https://developer.apple.com/documentation/uikit/uiwindowscene/requestgeometryupdate(_:errorhandler:)
  rotateScene(value) { return main(() => {
    const type = ObjC.classes.UIWindowSceneGeometryPreferencesIOS;
    if (!type) throw new Error('Scene geometry rotation requires iOS 16+');
    const scenes = ObjC.classes.UIApplication.sharedApplication().connectedScenes().allObjects();
    for (let i = 0; i < Number(scenes.count()); i++) {
      const scene = scenes.objectAtIndex_(i);
      if (Number(scene.activationState()) !== 0) continue;
      const preferences = type.alloc().initWithInterfaceOrientations_(1 << value);
      try { scene.requestGeometryUpdateWithPreferences_errorHandler_(preferences, ptr(0)); }
      finally { preferences.release(); }
      return;
    }
    throw new Error('No foreground active window scene');
  }); },
  idle(value) { return main(() => {
    const app = ObjC.classes.UIApplication.sharedApplication();
    const previous = Boolean(app.isIdleTimerDisabled());
    app.setIdleTimerDisabled_(value);
    return previous;
  }); }
};
