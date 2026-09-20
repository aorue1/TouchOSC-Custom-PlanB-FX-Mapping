# Vendored third-party layout components

## `colorpicker-swatches.tosc`

The "colorpicker swatches" module from
[tshoppa/touchOSC](https://github.com/tshoppa/touchOSC), MIT licensed,
copyright (c) 2023 Schulzki. See `LICENSE.tshoppa-touchOSC`.

`tools/vendor.py` lifts the `ColorPicker` group out of this file at build time
and grafts it into the generated layout, re-framed to the document and with its
dialog re-centred. The component's own controls and scripts are used unmodified,
so it keeps working exactly as its author documented:

```lua
ColorPicker:notify('pickColor', { callback = aControl, initial = aColor })
```

The caller is then notified with `colorPicked` (repeatedly, as the colour is
dragged) or `colorPickCanceled`.

It is checked in rather than fetched during the build so the layout can be
rebuilt without network access, and so an upstream change cannot silently alter
the surface.
