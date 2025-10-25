// This extension takes any htmx request which came from an element with the `hx-fragment` attribute, and adds its 
// value as a header in the request.
// The goal is to add some control into the HTML, for the fragment that is being rendered to replace the current HTML
// 'Content' is the default fragment name, which will be rendered in the case of an `hx-request`, but this attribute
// allows that to be overwritten at the HTML level
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
