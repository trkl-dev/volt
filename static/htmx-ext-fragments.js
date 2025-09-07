(function() {
    htmx.defineExtension('fragments', {
        onEvent: function(name, evt) {
            if (name !== 'htmx:configRequest') {
                return
            }
            const item = evt.detail.elt.attributes.getNamedItem("hx-fragment");
            if (item == null) {
                return;
            }
            evt.detail.headers['HX-Fragment'] = item.value;
        }
    })
})()
