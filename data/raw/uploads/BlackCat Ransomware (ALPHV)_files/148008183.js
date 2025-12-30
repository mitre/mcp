(function(w,d,c,k,a,b,t,e,h,s) {
    var cs = d.currentScript;
    if (cs) {
        var uo = cs.getAttribute('data-ueto');
        if (uo && w[uo] && typeof w[uo].setUserSignals === 'function') {
            w[uo].setUserSignals({'ea': c, 'kc': k, 'at': a, 'bi': b, 'pt': t, 'ec': e, 'ah': h, 'sb': s});
        }
    }
})(window, document, false, false, false, false, false, false, false, false);
