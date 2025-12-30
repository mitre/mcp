/******/ (function() { // webpackBootstrap
/******/ 	"use strict";
var __webpack_exports__ = {};

// UNUSED EXPORTS: default

;// CONCATENATED MODULE: ./src/location-service.ts
// FUTURE -- consider making this injectable
var LocationService = /** @class */ (function () {
    function LocationService() {
    }
    LocationService.setLocation = function (url) {
        window.location = url;
    };
    LocationService.reload = function () {
        window.location.reload();
    };
    LocationService.getHash = function () {
        return window.location.hash;
    };
    LocationService.setHash = function (hash) {
        window.location.hash = hash;
    };
    LocationService.getHref = function () {
        return window.location.href;
    };
    LocationService.setHref = function (url) {
        window.location.href = url;
    };
    LocationService.getPathname = function () {
        return window.location.pathname;
    };
    LocationService.getProtocol = function () {
        return window.location.protocol;
    };
    LocationService.getHostname = function () {
        return window.location.hostname;
    };
    return LocationService;
}());


;// CONCATENATED MODULE: ./src/helpers.ts

var Helpers = /** @class */ (function () {
    function Helpers() {
        this.UP = 38;
        this.DOWN = 40;
        this.ENTER = 13;
        this.ESC = 27;
        this.TAB = 9;
        this.BACKSPACE = 8;
        this.DELETE = 46;
    }
    Helpers.prototype.getKey = function (e) {
        if (window.event) {
            return e.keyCode;
        }
        else if (e.which) {
            return e.which;
        }
    };
    Helpers.prototype.isMac = function () {
        return navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    };
    Helpers.prototype.addClass = function (el, className) {
        if (el) {
            if (!this.hasClass(el, className)) {
                el.className = el.className + " " + className;
            }
        }
    };
    Helpers.prototype.removeClass = function (el, className) {
        if (el) {
            if (el.classList) {
                el.classList.remove(className);
            }
            else {
                el.className = el.className.replace(new RegExp('(^|\\b)' + className.split(' ').join('|') + '(\\b|$)', 'gi'), ' ');
            }
        }
    };
    Helpers.prototype.hasClass = function (el, className) {
        if (el) {
            var match = el.className.match(className);
            return match ? true : false;
        }
        return false;
    };
    Helpers.prototype.removeElement = function (elemId) {
        var elem = document.getElementById(elemId);
        if (elem != null) {
            elem.parentNode.removeChild(elem);
        }
    };
    Helpers.prototype.removeAttributesWithSelector = function (attrName, attrValue) {
        if (!attrName == null || !attrValue == null) {
            return;
        }
        var selector = "*[" + attrName + "=\"" + attrValue + "\"]";
        var matchingElements = document.querySelectorAll(selector);
        // iterate backwards because matchingElements is a live collection and we're actively changing the length as items are removed
        for (var i = matchingElements.length - 1; i >= 0; i--) {
            var el = matchingElements[i];
            el.removeAttribute(attrName);
        }
    };
    Helpers.prototype.addElement = function (el, className, id, role) {
        var elem = document.createElement("div");
        if (typeof className !== 'undefined' && className !== '') {
            elem.className = className;
        }
        if (typeof id !== 'undefined' && id !== '') {
            elem.setAttribute('id', id);
        }
        if (typeof role !== 'undefined' && role !== '') {
            elem.setAttribute('role', role);
        }
        el.appendChild(elem);
        return elem;
    };
    Helpers.prototype.addLabelElement = function (el, forAtt, value) {
        var label = document.createElement("label");
        label.setAttribute('for', forAtt);
        label.innerHTML = value;
        el.appendChild(label);
        return label;
    };
    Helpers.prototype.addInputElement = function (el, name, className, value, id, autocompleteDefaultVal) {
        var input = document.createElement("input");
        input.setAttribute('type', 'search');
        input.id = id;
        input.name = name;
        input.className = className;
        input.setAttribute('value', value);
        input.autocomplete = autocompleteDefaultVal;
        el.appendChild(input);
        return input;
    };
    Helpers.prototype.addButtonElement = function (el, className, id, value, title, accessibilityLabel) {
        var button = document.createElement("button");
        button.setAttribute('type', 'button');
        button.innerHTML = value;
        if (className) {
            button.className = className;
        }
        if (title) {
            button.title = title;
        }
        if (id) {
            button.id = id;
        }
        if (accessibilityLabel) {
            button.setAttribute('aria-label', accessibilityLabel);
        }
        el.appendChild(button);
        return button;
    };
    Helpers.prototype.addCssStyles = function (css) {
        var sheet = document.createElement('style');
        (document.head || document.getElementsByTagName('head')[0]).appendChild(sheet);
        sheet.setAttribute('type', 'text/css');
        sheet.appendChild(document.createTextNode(css));
    };
    Helpers.prototype.getWindowLocation = function () {
        return LocationService.getHref();
    };
    Helpers.prototype.getWindowHash = function () {
        return LocationService.getHash();
    };
    Helpers.prototype.getPredefinedFacet = function (boxId, i) {
        return document.getElementById(boxId).querySelectorAll('input[type=hidden]')[i].getAttribute("data-facet");
    };
    Helpers.prototype.getURLParam = function (param, doNotDecode) {
        if (!param) {
            return '';
        }
        var hash = this.getWindowHash();
        var lowerParam = param.toLowerCase();
        if (hash.indexOf('#%3F') !== -1) {
            hash = hash.replace('#%3F', '#?');
        }
        if (hash.toLowerCase().indexOf(lowerParam) == -1) {
            return '';
        }
        while (hash.indexOf('#?') != -1) {
            hash = hash.replace('#?', '&');
        }
        var rawQueryParams = hash.split('&');
        for (var i = rawQueryParams.length - 1; i >= 0; i--) {
            var kvp = rawQueryParams[i]
                .replace('?', '') // Clean up
                .replace('#', '') // Clean up
                .split('='); // Create kvp array in form of [{KEY}, {VALUE}]
            if (kvp.length < 2) {
                // We had a query parameter without an equals
                continue;
            }
            if (kvp[0].toLowerCase() == lowerParam) {
                return !doNotDecode ? decodeURIComponent(kvp[1]) : kvp[1];
            }
        }
        return '';
    };
    Helpers.prototype.stripHtmlTags = function (query) {
        if (query == null) {
            return query;
        }
        var tagBody = '(?:[^"\'>]|"[^"]*"|\'[^\']*\')*';
        var tagOrComment = new RegExp('<(?:'
            // Comment body.
            + '!--(?:(?:-*[^->])*--+|-?)'
            // Special "raw text" elements whose content should be elided.
            + '|script\\b' + tagBody + '>[\\s\\S]*?</script\\s*'
            + '|style\\b' + tagBody + '>[\\s\\S]*?</style\\s*'
            // Regular name
            + '|/?[a-z]'
            + tagBody
            + ')>', 'gi');
        var origQuery;
        do {
            origQuery = query;
            query = query.replace(tagOrComment, '');
        } while (query !== origQuery);
        if (query.indexOf("<") > -1) {
            query = query.replace(/<|>/g, '');
        }
        return query;
    };
    Helpers.prototype.stripSpecialChars = function (query) {
        return query.replace(/[–—―,.+?:-]/g, ' ');
    };
    Helpers.prototype.trim = function (s) {
        if (typeof String.prototype.trim !== 'function') {
            return s.replace(/^\s+|\s+$/g, '');
        }
        else {
            return s.trim();
        }
    };
    Helpers.prototype.removeUnsafeCharacters = function (query) {
        var reDoubleQuoteCharacter = /"/ig;
        var count = (query.match(reDoubleQuoteCharacter) || []).length;
        // remove " characters if there's odd number of matches
        if (count % 2) {
            query = query.replace(reDoubleQuoteCharacter, "");
        }
        // replace ' +' at the end of the query with '+' to avoid triggering of search tools
        query = query.replace(/ (\+)+$/g, "");
        return query;
    };
    Helpers.prototype.highlightSearchword = function (input, needle) {
        try {
            var pattern = new RegExp('(^|\\s)(' + needle + ')(|$)', 'ig');
            return input.replace(pattern, '$1<b>$2</b>$3');
        }
        catch (error) {
            // catch errors created by searches that use RegExp characters like *,+,\d, etc.
            return input;
        }
    };
    Helpers.prototype.objectToQueryString = function (obj) {
        var parts = [];
        for (var i in obj) {
            if (Object.prototype.hasOwnProperty.call(obj, i)) {
                parts.push(encodeURIComponent(i) + "=" + encodeURIComponent(obj[i]));
            }
        }
        return parts.join("&");
    };
    Helpers.prototype.isEmpty = function (object) {
        for (var i in object) {
            return false;
        }
        return true;
    };
    Helpers.prototype.isMobile = function () {
        var w = window.innerWidth;
        return w < 767 ? true : false;
    };
    Helpers.prototype.isTablet = function () {
        var w = window.innerWidth;
        return w > 767 && w >= 940 ? true : false;
    };
    /** Check if browser is Safari */
    Helpers.prototype.isBrowserSafari = function () {
        var ua = window.navigator.userAgent;
        return (ua.indexOf("Safari") > -1) && !(ua.indexOf("Chrome") > -1);
    };
    /** Handles duplicating words bug in Safari 15 */
    Helpers.prototype.removeDuplicateTranscript = function (final_transcript) {
        var transcript = final_transcript.toLowerCase();
        var numWords = transcript.split(' ').length;
        if ((numWords & 2) !== 0) {
            return transcript;
        }
        var firstHalf = transcript.substring(0, transcript.length / 2).split(' ').join('');
        var secondHalf = transcript.substring(transcript.length / 2, transcript.length).split(' ').join('');
        if (firstHalf === secondHalf) {
            return transcript.substring(0, transcript.length / 2);
        }
        else {
            return transcript;
        }
    };
    Helpers.prototype.shadeColor = function (color, percent) {
        var R = parseInt(color.substring(1, 3), 16);
        var G = parseInt(color.substring(3, 5), 16);
        var B = parseInt(color.substring(5, 7), 16);
        R = Math.floor(R * (100 + percent));
        G = Math.floor(G * (100 + percent));
        B = Math.floor(B * (100 + percent));
        R = (R < 255) ? R : 255;
        G = (G < 255) ? G : 255;
        B = (B < 255) ? B : 255;
        var RR = ((R.toString(16).length == 1) ? "0" + R.toString(16) : R.toString(16));
        var GG = ((G.toString(16).length == 1) ? "0" + G.toString(16) : G.toString(16));
        var BB = ((B.toString(16).length == 1) ? "0" + B.toString(16) : B.toString(16));
        return "#" + RR + GG + BB;
    };
    Helpers.prototype.closest = function (el, selector) {
        if ('undefined' === typeof Element.prototype.closest) {
            // closest polyfill
            Element.prototype.closest = Element.prototype.closest ||
                function (selector) {
                    var el = this;
                    while (el.matches && !el.matches(selector)) {
                        el = el.parentNode;
                    }
                    return el.matches ? el : null;
                };
        }
        return el.closest(selector);
    };
    Helpers.prototype.pageCanScroll = function (bottomOffset) {
        var windowHeight = window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight;
        var documentHeight = document.documentElement.scrollHeight;
        return (documentHeight - bottomOffset > windowHeight);
    };
    /** Builds and returns a speech grammar list from a list of words */
    Helpers.prototype.buildRecognitionGrammar = function (words) {
        var SpeechGrammarList = window.SpeechGrammarList || window['webkitSpeechGrammarList'];
        if (SpeechGrammarList) {
            var grammar = '#JSGF V1.0; grammar words; public <words> = ' + words.join(' | ') + ' ;';
            var grammarList = new SpeechGrammarList();
            grammarList.addFromString(grammar, 1);
            return grammarList;
        }
    };
    Helpers.prototype.getElementById = function (elementId, pierceShadowDom, parentElement) {
        if (!parentElement) {
            parentElement = document;
        }
        if (pierceShadowDom) {
            // do some simple validation that elementId could actually be an element id and not a selector
            if (elementId.indexOf(' ') !== -1 ||
                elementId.indexOf('.') !== -1 ||
                elementId.indexOf('#') !== -1) {
                return undefined;
            }
            return this.getElementByIdShadowDom(elementId, parentElement);
        }
        else {
            return parentElement.getElementById(elementId);
        }
    };
    Helpers.prototype.getElementByIdShadowDom = function (elementId, parentElement) {
        if (!parentElement) {
            parentElement = document;
        }
        var nonShadowMatch = parentElement.getElementById(elementId);
        if (nonShadowMatch) {
            return nonShadowMatch;
        }
        var customElements = parentElement.querySelectorAll('*');
        for (var i = 0; i < customElements.length; i++) {
            var customElement = customElements[i];
            if (customElement.shadowRoot) {
                var shadowDomMatch = this.getElementByIdShadowDom(elementId, customElement.shadowRoot);
                if (shadowDomMatch) {
                    return shadowDomMatch;
                }
            }
        }
        return undefined;
    };
    /**
     * @returns the first HTML node ancestor of the input element that doesn't contain a ShadowRoot attached.
     *
     * The function recursively inspects every parent node until it finds an element without a ShadowRoot attached.
     * If the final element is the <body>, then the return type is switched to HTMLDocument (represented in the DOM as the <html> tag).
     */
    Helpers.prototype.findNonShadowAncestor = function (element) {
        while (element.shadowRoot) {
            element = element.parentElement;
            if (element === null) {
                return document;
            }
        }
        return element;
    };
    Helpers.prototype.querySelector = function (selector, pierceShadowDom, parentElement) {
        if (!parentElement) {
            parentElement = document;
        }
        if (pierceShadowDom) {
            return this.querySelectorShadowDom(selector, parentElement);
        }
        else {
            return parentElement.querySelector(selector);
        }
    };
    Helpers.prototype.querySelectorShadowDom = function (selector, parentElement) {
        if (!parentElement) {
            parentElement = document;
        }
        var nonShadowMatch = parentElement.querySelector(selector);
        if (nonShadowMatch) {
            return nonShadowMatch;
        }
        var customElements = parentElement.querySelectorAll('*');
        for (var i = 0; i < customElements.length; i++) {
            var customElement = customElements[i];
            if (customElement.shadowRoot) {
                var shadowDomMatch = this.querySelectorShadowDom(selector, customElement.shadowRoot);
                if (shadowDomMatch) {
                    return shadowDomMatch;
                }
            }
        }
        return undefined;
    };
    Helpers.prototype.querySelectorAll = function (selector, pierceShadowDom, parentElement) {
        if (!parentElement) {
            parentElement = document;
        }
        if (pierceShadowDom) {
            return this.querySelectorAllShadowDom(selector, parentElement);
        }
        else {
            return Array.from(parentElement.querySelectorAll(selector));
        }
    };
    Helpers.prototype.querySelectorAllShadowDom = function (selector, parentElement) {
        if (!parentElement) {
            parentElement = document;
        }
        var matches = parentElement.querySelectorAll(selector);
        var elementMatches = [];
        for (var i = 0; i < matches.length; i++) {
            var match = matches[i];
            elementMatches.push(match);
        }
        var customElements = parentElement.querySelectorAll('*');
        for (var i = 0; i < customElements.length; i++) {
            var customElement = customElements[i];
            if (customElement.shadowRoot) {
                var shadowDomMatches = this.querySelectorAllShadowDom(selector, customElement.shadowRoot);
                for (var j = 0; j < shadowDomMatches.length; j++) {
                    elementMatches.push(shadowDomMatches[j]);
                }
            }
        }
        return elementMatches;
    };
    Helpers.prototype.cloneObject = function (sourceObject) {
        if (!sourceObject) {
            return sourceObject;
        }
        return JSON.parse(JSON.stringify(sourceObject));
    };
    Helpers.flattenCollection = function (collection, key) {
        var flatten = {};
        if (collection.length === 0) {
            flatten[key] = null;
            return flatten;
        }
        var i = 0;
        for (i = 0; i < collection.length; i++) {
            var itemKey = key + "[" + i + "]";
            var item = collection[i];
            var flattenItems = Helpers.flatten(item, itemKey);
            Helpers.mergeOptions(flatten, flattenItems);
        }
        return flatten;
    };
    Helpers.flattenObject = function (object, key) {
        var flatten = {};
        var isEmpty = Object.keys(object).length === 0;
        if (isEmpty) {
            flatten[key] = null;
            return flatten;
        }
        for (var property in object) {
            var itemKey = void 0;
            if (key) {
                itemKey = key + "." + property;
            }
            else {
                itemKey = property;
            }
            var item = object[property];
            var flattedProperties = Helpers.flatten(item, itemKey);
            Helpers.mergeOptions(flatten, flattedProperties);
        }
        return flatten;
    };
    Helpers.flatten = function (item, key) {
        var flatten = {};
        if (item instanceof Array) {
            flatten = Helpers.flattenCollection(item, key);
        }
        else if (item instanceof Object) {
            flatten = Helpers.flattenObject(item, key);
        }
        else {
            if (key) {
                flatten[key] = item;
            }
            else {
                flatten = item;
            }
        }
        return flatten;
    };
    Helpers.mergeOptions = function (source, toBeMerged) {
        for (var attrname in toBeMerged) {
            source[attrname] = toBeMerged[attrname];
        }
    };
    /** Converts our wildcard syntax into RegExp */
    Helpers.wildcardToRegex = function (pattern) {
        var escapedPattern = Helpers.escapeRegex(pattern); // Escapes all RegExp reserved characters
        var specialSyntaxPattern = escapedPattern.replace(/\\\*/g, '.*').replace(/\\\?/g, '.'); // Un-escapes our special syntax
        return new RegExp("^" + specialSyntaxPattern + "$");
    };
    /** Escapes all "reserved" characters for RegExp */
    Helpers.escapeRegex = function (str) {
        return str.replace(/[/\-\\^$*+?.()|[\]{}]/g, '\\$&');
    };
    return Helpers;
}());


;// CONCATENATED MODULE: ./src/translate-provider.ts
var TranslateProvider = /** @class */ (function () {
    function TranslateProvider() {
        this.language = "da";
        this.translations = {
            "da": {
                "did_you_mean": "Mente du <a href='' aria-label='Mente du {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Din søgning på '<b>{{value}}</b>' ",
                "total_results": "gav <b>{{value}}</b> resultater",
                "total_result": "gav <b>{{value}}</b> resultat",
                "in_category": " i kategorien <b>{{value}}</b>",
                "and": " og",
                "searched_instead": "<br />Viser i stedet <b>{{number}}</b> resultater for <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Beklager, vi stødte på en uventet fejl. Prøv venligst igen senere.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Indtast venligst søgeord</div>",
                "overlay_close_div": "ESC eller",
                "overlay_close_button": "Luk",
                "load_more": "vis flere",
                "poweredBy_title": "Tag kontrol over din søgemaskine - Cludo",
                "backToTop": "Tilbage til toppen",
                "search_input_label": "Søg",
                "search_button_text": "Søg",
                "overlay_close_button_title": "Luk",
                "template_all_results": "Alle resultater",
                "template_suggestions": "Forslag",
                "template_search_results": "Søgeresultater",
                "template_autocomplete_hint": "Søgeforslag er tilgængelige. Brug op- og ned-pilene for at gennemgå disse, og tast enter for at vælge.",
                "related_searches_title": "Relaterede søgninger",
                "suggested_searches_title": "Søgeforslag",
                "recent_searches_title": "Seneste søgninger",
                "template_nrm_use_another_search_word": "Prøv et andet søgeord",
                "template_nrm_try_to_search": "Prøv samme søgning",
                "template_nrm_without_filters": "uden filtre",
                "template_nrm_display": "Vis",
                "template_nrm_all_results": "alle resultater",
                "toggle_filters_label": "Vis/Skjul søgefiltre",
                "voice_search_title": "Stemmesøgning",
                "search_filters": "Søgefiltre",
                "loading_results": "Indlæser søgeresultater",
                "general_page": "Side",
                "next_page": "Næste side",
                "prev_page": "Foregående side",
                "general_relevance": "Relevans"
            },
            "en": {
                "did_you_mean": "Did you mean <a href='' aria-label='Did you mean {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Your search for '<b>{{value}}</b>' ",
                "total_results": "returned <b>{{value}}</b> results",
                "total_result": "returned <b>{{value}}</b> result",
                "in_category": " in the category <b>{{value}}</b>",
                "and": " and",
                "searched_instead": "<br />Showing <b>{{number}}</b> results for <b>{{term}}</b> instead",
                "error": "<p style='color: red' class='cludo-error-message'>Apologies, we encountered an unexpected error. Please try again at a later time.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Please enter a search term</div>",
                "overlay_close_div": "ESC or",
                "overlay_close_button": "Close",
                "load_more": "show more",
                "poweredBy_title": "Take control over the search on your website - Cludo",
                "backToTop": "Back to top",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Close",
                "template_all_results": "All Results",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Related Searches",
                "suggested_searches_title": "Suggested searches",
                "recent_searches_title": "Recent searches",
                "template_nrm_use_another_search_word": "Try another search word",
                "template_nrm_try_to_search": "Try to search",
                "template_nrm_without_filters": "without filters",
                "template_nrm_display": "Display",
                "template_nrm_all_results": "all results",
                "toggle_filters_label": "Toggle search filters",
                "voice_search_title": "Search by voice",
                "search_filters": "Search Filters",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "de": {
                "did_you_mean": "Meinten Sie <a href='' aria-label='Meinten Sie {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Ihre Suche nach '<b>{{value}}</b>' ",
                "total_results": "ergab <b>{{value}}</b> Ergebnisse",
                "total_result": "ergab  <b>{{value}}</b> Ergebnis",
                "in_category": " in Kategorie <b>{{value}}</b>",
                "and": " und",
                "searched_instead": "<br />Stattdessen werden <b>{{number}}</b> Ergebnisse für <b>{{term}}</b> angezeigt",
                "error": "<p style='color: red' class='cludo-error-message'>Tut uns leid, es ist ein Fehler aufgetreten.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Bitte geben Sie einen Suchbegriff ein</div>",
                "overlay_close_div": "ESC oder",
                "overlay_close_button": "Schließen",
                "load_more": "Mehr anzeigen",
                "poweredBy_title": "Übernehmen Sie die Kontrolle über die Suche auf Ihrer Website - Cludo",
                "backToTop": "Nach oben",
                "search_input_label": "Suche",
                "search_button_text": "Suche",
                "overlay_close_button_title": "Schließen",
                "template_all_results": "Alle Ergebnisse",
                "template_suggestions": "Vorschläge",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Verwandte Suchanfragen",
                "suggested_searches_title": "Vorgeschlagene Suchanfragen",
                "recent_searches_title": "Letzte Suchanfragen",
                "template_nrm_use_another_search_word": "Versuche einen anderen Suchbegriff",
                "template_nrm_try_to_search": "Versuchen sie zu suchen",
                "template_nrm_without_filters": "ohne filter",
                "template_nrm_display": "Anzeige",
                "template_nrm_all_results": "alle Ergebnisse",
                "toggle_filters_label": "Suchfilter umschalten",
                "voice_search_title": "Sprachsuche",
                "search_filters": "Suchfilter",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "nl": {
                "did_you_mean": "Bedoelde je <a href='' aria-label='Bedoelde je {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Uw zoektocht naar '<b>{{value}}</b>' ",
                "total_results": "gaf <b>{{value}}</b> resultaten",
                "total_result": "gaf <b>{{value}}</b> resultaat",
                "in_category": " in de categorie <b>{{value}}</b>",
                "and": " en",
                "searched_instead": "<br />In plaats daarvan <b>{{number}}</b> resultaten weergeven voor <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Sorry, er is een fout opgetreden.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Vul een zoekterm in</div>",
                "overlay_close_div": "ESC of",
                "overlay_close_button": "sluiten",
                "load_more": "laat meer zien",
                "poweredBy_title": "Aangedreven door - Cludo",
                "backToTop": "Terug naar boven",
                "search_input_label": "Zoeken",
                "search_button_text": "Zoeken",
                "overlay_close_button_title": "sluiten",
                "template_all_results": "Alle resultaten",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Verwante zoekopdrachten",
                "suggested_searches_title": "Suggested zoekopdrachten",
                "recent_searches_title": "Recent zoekopdrachten",
                "template_nrm_use_another_search_word": "Probeer een ander zoekwoord",
                "template_nrm_try_to_search": "Probeer te zoeken",
                "template_nrm_without_filters": "zonder filters",
                "template_nrm_display": "Weergave",
                "template_nrm_all_results": "alle resultaten",
                "toggle_filters_label": "Schakel zoekfilters in",
                "voice_search_title": "Zoek bij stem",
                "search_filters": "Zoekfilters",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "sv": {
                "did_you_mean": "Menade du <a href='' aria-label='Menade du {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Din sökning på '<b>{{value}}</b>' ",
                "total_results": "gav <b>{{value}}</b> resultat",
                "total_result": "gav <b>{{value}}</b> resultat",
                "in_category": " i kategorin <b>{{value}}</b>",
                "and": " och",
                "searched_instead": "<br />Visar <b>{{number}}</b> resultat för istället <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Beklagar, men ett oväntat fel har inträffat. Försök igen om ett litet tag.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Ange sökord</div>",
                "overlay_close_div": "ESC eller",
                "overlay_close_button": "Stänga",
                "load_more": "visa fler",
                "poweredBy_title": "Ta kontroll över din sökmotor - Cludo",
                "backToTop": "Tillbaka till toppen",
                "search_input_label": "Sök",
                "search_button_text": "Sök",
                "overlay_close_button_title": "Stänga",
                "template_all_results": "Alla resultat",
                "template_suggestions": "Förslag",
                "template_search_results": "Sökresultat",
                "template_autocomplete_hint": "Autofullständiga resultat är tillgängliga. Använd upp och ner pilar för att granska och 'Enter' för att välja.",
                "related_searches_title": "Relaterade sökningar",
                "suggested_searches_title": "Suggested sökningar",
                "recent_searches_title": "Recent sökningar",
                "template_nrm_use_another_search_word": "Försök med ett annat sökord",
                "template_nrm_try_to_search": "Försök att söka",
                "template_nrm_without_filters": "utan filter",
                "template_nrm_display": "Visa",
                "template_nrm_all_results": "alla resultat",
                "toggle_filters_label": "Växla sökfilter",
                "voice_search_title": "Sök med rösten",
                "search_filters": "Sökfilter",
                "loading_results": "Loading search results",
                "general_page": "Sida",
                "next_page": "Nästa sida",
                "prev_page": "Föregående sida",
                "general_relevance": "Relevans",
            },
            "el": {
                "did_you_mean": "Μήπως εννοείτε <a href='' aria-label='Μήπως εννοείτε {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "H αναζήτησή σας για '<b>{{value}}</b>' ",
                "total_results": "έδωσε <b>{{value}}</b> αποτελέσματα",
                "total_result": "έδωσε <b>{{value}}</b> αποτέλεσμα",
                "in_category": " στην κατηγορία <b>{{value}}</b>",
                "and": "και",
                "searched_instead": "<br />Εμφανίζονται αποτελέσματα για <b>{{number}}</b> αντί αυτού και έδωσε <b>{{term}}</b> αποτελέσματα",
                "error": "<p style='color: red' class='cludo-error-message'>Λυπούμαστε, παρουσιάστηκε ένα σφάλμα.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Παρακαλούμε εισάγετε έναν όρο αναζήτησης</div>",
                "overlay_close_div": "Πατήστε ESC ή",
                "overlay_close_button": "κλείνω",
                "load_more": "δείξτε περισσότερα",
                "poweredBy_title": "Πάρτε τον έλεγχο της αναζήτησης στην ιστοσελίδα σας - Cludo",
                "backToTop": "Επιστροφή στην κορυφή",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "κλείνω",
                "template_all_results": "Όλα τα αποτελέσματα",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Σχετικές αναζητήσεις",
                "suggested_searches_title": "Suggested αναζητήσεις",
                "recent_searches_title": "Recent αναζητήσεις",
                "template_nrm_use_another_search_word": "Δοκιμάστε άλλη λέξη αναζήτησης",
                "template_nrm_try_to_search": "Προσπαθήστε να ψάξετε",
                "template_nrm_without_filters": "χωρίς φίλτρα",
                "template_nrm_display": "Απεικόνιση",
                "template_nrm_all_results": "όλα τα αποτελέσματα",
                "toggle_filters_label": "Εναλλαγή φίλτρων αναζήτησης",
                "voice_search_title": "Αναζήτηση με φωνή",
                "search_filters": "Φίλτρα αναζήτησης",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "ar": {
                "did_you_mean": "هل تقصد <a href='' aria-label='هل تقصد {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "تبحث عن '<b>{{value}}</b>' ",
                "total_results": "نتيجة <b>{{value}}</b> أعطى",
                "total_result": "<b>{{value}}</b> أعطى نتيجة واحدة",
                "in_category": " في الفئة <b>{{value}}</b>",
                "and": " و",
                "searched_instead": "<br />يتم عرض <b>{{number}}</b> نتائج ل <b>{{term}}</b> بدلاً من ذلك.",
                "error": "<p style='color: red' class='cludo-error-message'>معذرة، حدث خطأ.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>يرجى إدخال مصطلح بحث</div>",
                "overlay_close_div": "ESC أو",
                "overlay_close_button": "غلق",
                "load_more": "عرض المزيد",
                "poweredBy_title": "سيطر على البحث على موقعك الإلكتروني - Cludo",
                "backToTop": "رجوع إلى أعلى",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "غلق",
                "template_all_results": "جميع النتائج",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "عمليات البحث ذات الصلة",
                "suggested_searches_title": "عمليات البحث المقترحة",
                "recent_searches_title": "عمليات البحث الأخيرة",
                "template_nrm_use_another_search_word": "جرب كلمة بحث أخرى",
                "template_nrm_try_to_search": "حاول البحث",
                "template_nrm_without_filters": "بدون مرشحات",
                "template_nrm_display": "عرض",
                "template_nrm_all_results": "جميع النتائج",
                "toggle_filters_label": "تبديل عوامل تصفية البحث",
                "voice_search_title": "البحث عن طريق الصوت",
                "search_filters": "مرشحات البحث",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "hy": {
                "did_you_mean": "Միգուցե նկատի ունեք <a href='' aria-label='Միգուցե նկատի ունեք {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Ձեր '<b>{{value}}</b>' բառի որոնումը",
                "total_results": "տվեց <b>{{value}}</b> արդյունք",
                "total_result": "տվեց <b>{{value}}</b> արդյունք",
                "in_category": "<b>{{value}}</b> բաժնում",
                "and": "և",
                "searched_instead": "<br /> Փոխարենը ցուցադրվում են <b>{{number}}</b> արդյունքները <b>{{term}}</b>-ի համար",
                "error": "<p style='color: red' class='cludo-error-message'>Ցավում ենք, սխալմունք է տեղի ունեցել</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Մուտքագրեք խնդրեմ որոնման չափանիշները</div>",
                "overlay_close_div": "ESC կամ",
                "overlay_close_button": "ավարտ",
                "load_more": "ցույց տալ ավելին",
                "poweredBy_title": "Ձեր կայքում վերահսկեք Cludo բառի որոնումը",
                "backToTop": "Վերադառնալ սկիզբ",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "ավարտ",
                "template_all_results": "Բոլոր արդյունքները",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Առնչվող որոնումներ",
                "suggested_searches_title": "Առաջարկվող որոնումներ",
                "recent_searches_title": "Վերջին որոնումները",
                "template_nrm_use_another_search_word": "Փորձեք մեկ այլ որոնման բառ",
                "template_nrm_try_to_search": "Փորձեք որոնել",
                "template_nrm_without_filters": "առանց ֆիլտրերի",
                "template_nrm_display": "Ցուցադրել",
                "template_nrm_all_results": "բոլոր արդյունքները",
                "toggle_filters_label": "Միացնել որոնման զտիչները",
                "voice_search_title": "Որոնել ձայնով",
                "search_filters": "Որոնման զտիչներ",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "eu": {
                "did_you_mean": "<a href='' aria-label='{{value}} esan nahi al duzu'><b>{{value}}</b></a> esan nahi al duzu?",
                "your_search_on": " '<b>{{value}}</b>' bilaketak",
                "total_results": "<b>{{value}}</b> emaitza eman ditu",
                "total_result": "emaitza <b>{{value}}</b> eman du",
                "in_category": " <b>{{value}}</b> kategorian",
                "and": "eta",
                "searched_instead": "<br />Horren ordez, <b>{{number}}</b> emaitzak erakusten ditu <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Barkatu, errore bat gertatu da.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Idatzi bilaketa-termino bat</div>",
                "overlay_close_div": "ESC edo",
                "overlay_close_button": "Itxi",
                "load_more": "gehiago erakutsi",
                "poweredBy_title": "Kontrola itzazu zure webguneko bilaketak - Cludo",
                "backToTop": "Gora itzuli",
                "search_input_label": "Sök",
                "search_button_text": "Sök",
                "overlay_close_button_title": "Itxi",
                "template_all_results": "Emaitza guztiak",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Lotutako bilaketak",
                "suggested_searches_title": "Iradokitako bilaketak",
                "recent_searches_title": "Azken bilaketak",
                "template_nrm_use_another_search_word": "Saiatu beste bilaketa-hitz bat",
                "template_nrm_try_to_search": "Saiatu bilatzen",
                "template_nrm_without_filters": "iragazkirik gabe",
                "template_nrm_display": "Bistaratzea",
                "template_nrm_all_results": "emaitza guztiak",
                "toggle_filters_label": "Aldatu bilaketa-iragazkiak",
                "voice_search_title": "Bilatu ahots bidez",
                "search_filters": "Bilaketa-iragazkiak",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "bg": {
                "did_you_mean": "Имахте предвид <a href='' aria-label='Имахте предвид {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Вашето търсене за '<b>{{value}}</b>' ",
                "total_results": "даде <b>{{value}}</b> резултата",
                "total_result": "даде <b>{{value}}</b> резултат",
                "in_category": "в категория <b>{{value}}</b>",
                "and": "и",
                "searched_instead": "<br />Вместо това виждате <b>{{number}}</b> резултата за <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>За съжаление, възникна грешка.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Въведете термин за търсене</div>",
                "overlay_close_div": "ESC или",
                "overlay_close_button": "Затвори",
                "load_more": "показване на още",
                "poweredBy_title": "Поемете контрол върху търсенето в уеб сайта си - Cludo",
                "backToTop": "Обратно най-горе",
                "search_input_label": "Търси",
                "search_button_text": "Търси",
                "overlay_close_button_title": "Затвори",
                "template_all_results": "Всички резултати",
                "template_suggestions": "Предложения",
                "template_search_results": "Резултати от търсенето",
                "template_autocomplete_hint": "Предложения за търсене. Използвайте стрелките на клавиатурата за да сменяте фокуса и Enter за да изберете.",
                "related_searches_title": "Подобни Търсения",
                "suggested_searches_title": "Предложени търсения",
                "recent_searches_title": "Скорошни търсения",
                "template_nrm_use_another_search_word": "Опитайте с друга дума за търсене",
                "template_nrm_try_to_search": "Опитайте се да търсите",
                "template_nrm_without_filters": "без филтри",
                "template_nrm_display": "Дисплей",
                "template_nrm_all_results": "всички резултати",
                "toggle_filters_label": "Покажи/скрий филтрите",
                "voice_search_title": "Гласово търсене",
                "search_filters": "Филтри за търсене",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "ca": {
                "did_you_mean": "Volia di <a href='' aria-label='Volia di {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "La seva cerca de '<b>{{value}}</b>' ",
                "total_results": "ha donat <b>{{value}}</b> resultats",
                "total_result": "ha donat <b>{{value}}</b> resultat",
                "in_category": " en la categoria <b>{{value}}</b>",
                "and": " i",
                "searched_instead": "<br />Es mostren <b>{{number}}</b> resultats per a <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Ens sap greu, s'ha produït un error.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Si us plau, introdueixi un terme de cerca</div>",
                "overlay_close_div": "ESC o",
                "overlay_close_button": "Tancar",
                "load_more": "mostrar-ne més",
                "poweredBy_title": "Controli les cerques en el seu lloc web - Cludo",
                "backToTop": "Tornar al començament",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Tancar",
                "template_all_results": "Tots els resultats",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Recerques relacionades",
                "suggested_searches_title": "Cerques suggerides",
                "recent_searches_title": "Cerques recents",
                "template_nrm_use_another_search_word": "Prova una altra paraula de cerca",
                "template_nrm_try_to_search": "Intenta cercar",
                "template_nrm_without_filters": "sense filtres",
                "template_nrm_display": "Mostra",
                "template_nrm_all_results": "tots els resultats",
                "toggle_filters_label": "Commuta els filtres de cerca",
                "voice_search_title": "Cerca per veu",
                "search_filters": "Filtres de cerca",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "zh": {
                "did_you_mean": "您是说 <a href='' aria-label='您是说 {{value}} 吗'><b>{{value}}</b></a> 吗？",
                "your_search_on": "您搜索 '<b>{{value}}</b>' ",
                "total_results": "给出 <b>{{value}}</b> 个结果",
                "total_result": "给出 <b>{{value}}</b> 个结果",
                "in_category": "在类别 <b>{{value}}</b> 中",
                "and": "并",
                "searched_instead": "<br /> 改为显示 '<b>{{number}}</b>' 的 <b>{{term}}</b> 结果",
                "error": "<p style='color: red' class='cludo-error-message'>抱歉，发生了一个错误。</p>",
                "no_search_term": "<div class='cludo-no-search-term'>请输入一个搜索术语</div>",
                "load_more": "显示更多",
                "poweredBy_title": "取得对您网站上搜索的控制 - Cludo",
                "backToTop": "返回顶部",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_div": "ESC 或者",
                "overlay_close_button": "关闭",
                "overlay_close_button_title": "关闭",
                "template_all_results": "所有結果",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "相关搜索",
                "suggested_searches_title": "建议搜索",
                "recent_searches_title": "最近搜索",
                "template_nrm_use_another_search_word": "尝试另一个搜索词",
                "template_nrm_try_to_search": "尝试搜索",
                "template_nrm_without_filters": "没有过滤器",
                "template_nrm_display": "展示",
                "template_nrm_all_results": "所有结果",
                "toggle_filters_label": "切换搜索过滤器",
                "voice_search_title": "语音搜索",
                "search_filters": "搜索过滤器",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "cs": {
                "did_you_mean": "Mysleli jste <a href='' aria-label='Mysleli jste {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Při vyhledávání '<b>{{value}}</b>' ",
                "total_results": "bylo nalezeno <b>{{value}}</b> výsledkù",
                "total_result": "nalezen <b>{{value}}</b> výsledek",
                "in_category": " v kategorii <b>{{value}}</b>",
                "and": " a",
                "searched_instead": "<br />Místo toho se zobrazují výsledky <b>{{number}}</b> pro <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Omlouváme se, stala se chyba.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Vložte prosím slovo, které chcete vyhledat</div>",
                "overlay_close_div": "ESC nebo",
                "overlay_close_button": "Zavřít",
                "load_more": "ukaž víc",
                "poweredBy_title": "Převezmìte kontrolu nad vyhledáváním na wašich webových stránkách - Cludo",
                "backToTop": "Zpět nahoru",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Zavřít",
                "template_all_results": "Svi rezultati",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Související vyhledávání",
                "suggested_searches_title": "Navrhovaná vyhledávání",
                "recent_searches_title": "Nedávná vyhledávání",
                "template_nrm_use_another_search_word": "Zkuste hledat jiné slovo",
                "template_nrm_try_to_search": "Zkuste hledat",
                "template_nrm_without_filters": "bez filtrů",
                "template_nrm_display": "Zobrazit",
                "template_nrm_all_results": "všechny výsledky",
                "toggle_filters_label": "Přepnout filtry vyhledávání",
                "voice_search_title": "Hledejte hlasem",
                "search_filters": "Filtry vyhledávání",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "et": {
                "did_you_mean": "Kas te mõtlete <a href='' aria-label='Kas te mõtlete {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Te otsite '<b>{{value}}</b>' ",
                "total_results": "pakutakse <b>{{value}}</b> tulemust",
                "total_result": "pakutakse <b>{{value}}</b> tulemus",
                "in_category": " kategoorias <b>{{value}}</b>",
                "and": " ja",
                "searched_instead": "<br />Selle asemel kuvatakse <b>{{number}}</b> tulemust päringule <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Vabandust, tekkis viga.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Palun sisestage otsitav mõiste</div>",
                "overlay_close_div": "ESC või",
                "overlay_close_button": "sulgema",
                "load_more": "näidake rohkem",
                "poweredBy_title": "Kontrollige oma veebisaidi otsinguid - Cludo",
                "backToTop": "Tagasi üles",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "sulgema",
                "template_all_results": "Kõik tulemused",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Seotud otsingud",
                "suggested_searches_title": "Soovitatud otsingud",
                "recent_searches_title": "Hiljutised otsingud",
                "template_nrm_use_another_search_word": "Proovi mõnda muud otsingusõna",
                "template_nrm_try_to_search": "Proovige otsida",
                "template_nrm_without_filters": "ilma filtriteta",
                "template_nrm_display": "Ekraan",
                "template_nrm_all_results": "kõik tulemused",
                "toggle_filters_label": "Lülitage otsingufiltrid sisse",
                "voice_search_title": "Otsige häälega",
                "search_filters": "Otsingufiltrid",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "fi": {
                "did_you_mean": "Tarkoititko sanaa <a href='' aria-label='Tarkoititko sanaa {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Hakusi sanalla '<b>{{value}}</b>' ",
                "total_results": "tuotti <b>{{value}}</b> tulosta",
                "total_result": "tuotti <b>{{value}}</b> tuloksen",
                "in_category": " kategoriassa <b>{{value}}</b>",
                "and": " ja",
                "searched_instead": "<br />Näytetään sen sijaan <b>{{number}}</b> tulosta haulle <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Pahoittelut, havaitsimme odottamattoman virheen. Yritä myöhemmin uudelleen.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Syötä hakutermi</div>",
                "overlay_close_div": "ESC tai",
                "overlay_close_button": "ummistaa",
                "load_more": "näytä lisää",
                "poweredBy_title": "Ota verkkosivustosi hakutoiminto haltuusi - Cludo",
                "backToTop": "Takaisin alkuun",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "ummistaa",
                "template_all_results": "Kaikki tulokset",
                "template_suggestions": "Hakuehdotukset",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Aiheeseen liittyvät haut",
                "suggested_searches_title": "Ehdotetut haut",
                "recent_searches_title": "Viimeaikaiset haut",
                "template_nrm_use_another_search_word": "Kokeile toista hakusanaa",
                "template_nrm_try_to_search": "Yritä etsiä",
                "template_nrm_without_filters": "ilman suodattimia",
                "template_nrm_display": "Näytä",
                "template_nrm_all_results": "kaikki tulokset",
                "toggle_filters_label": "Ota hakusuodattimet käyttöön",
                "voice_search_title": "Hae äänellä",
                "search_filters": "Hakusuodattimet",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "fr": {
                "did_you_mean": "Voulez-vous dire <a href='' aria-label='Voulez-vous dire {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Vous avez recherché '<b>{{value}}</b>' ",
                "total_results": "<b>{{value}}</b> occurrences trouvées",
                "total_result": "<b>{{value}}</b> occurrence trouvée",
                "in_category": " dans la catégorie <b>{{value}}</b>",
                "and": " et",
                "searched_instead": "<br />Afficher <b>{{number}}</b> les résultats pour <b>{{term}}</b> à la place",
                "error": "<p style='color: red' class='cludo-error-message'>Une erreur s'est produite.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Veuillez entrer un terme de recherche</div>",
                "overlay_close_div": "ESC ou",
                "overlay_close_button": "fermer",
                "load_more": "voir plus",
                "poweredBy_title": "Prenez le contrôle des recherches sur votre site Internet - Cludo",
                "backToTop": "Retour vers le haut",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "fermer",
                "template_all_results": "Tous les résultats",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Recherches associées",
                "suggested_searches_title": "Recherches suggérées",
                "recent_searches_title": "Recherches récentes",
                "template_nrm_use_another_search_word": "Essayer avec une autre recherche",
                "template_nrm_try_to_search": "Essayer de rechercher",
                "template_nrm_without_filters": "sans filtres",
                "template_nrm_display": "Afficher tous les résultats",
                "template_nrm_all_results": "tous les résultats",
                "toggle_filters_label": "Afficher/Masquer les filtres de recherche",
                "voice_search_title": "Recherche vocale",
                "search_filters": "Filtres de recherche",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "gl": {
                "did_you_mean": "¿Querías dicir <a href='' aria-label='¿Querías dicir {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "A tua busca de '<b>{{value}}</b>' ",
                "total_results": "  dou <b>{{value}}</b> resultados",
                "total_result": "  dou <b>{{value}}</b> resultado",
                "in_category": " na categoría <b>{{value}}</b>",
                "and": " e",
                "searched_instead": "<br />Mostrando <b>{{number}}</b> resultados para <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Sentímolo, houbo un erro.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Introduce un termo na busca</div>",
                "overlay_close_div": "ESC ou",
                "overlay_close_button": "Pechar",
                "load_more": "mostrar mais",
                "poweredBy_title": "Toma o control da busca no teu website - Cludo",
                "backToTop": "Volver arriba",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Pechar",
                "template_all_results": "Todos os resultados",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Buscas relacionadas",
                "suggested_searches_title": "Buscas sugeridas",
                "recent_searches_title": "Buscas recientes",
                "template_nrm_use_another_search_word": "Proba con outra palabra de busca",
                "template_nrm_try_to_search": "Tenta buscar",
                "template_nrm_without_filters": "sen filtros",
                "template_nrm_display": "Mostrar",
                "template_nrm_all_results": "todos os resultados",
                "toggle_filters_label": "Mostrar/esconder os filtros de busca",
                "voice_search_title": "Busca por voz",
                "search_filters": "Filtros de busca",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "hi": {
                "did_you_mean": "क्या आपका मतलब <a href='' aria-label='क्या आपका मतलब {{value}}' हैं><b>{{value}}</b></a> हैं?",
                "your_search_on": "आपकी '<b>{{value}}</b>' खोज ",
                "total_results": "  के लिए <b>{{value}}</b> परिणाम मिले",
                "total_result": "<b>{{value}}</b> परिणाम मिला",
                "in_category": "<b>{{value}}</b> श्रेणी में",
                "and": " और",
                "searched_instead": "<br />इसके बजाय <b>{{number}}</b> के लिए <b>{{term}}</b> परिणाम दिखाए जा रहे हैं।",
                "error": "<p style='color: red' class='cludo-error-message'>क्षमा करें, एक त्रुटी हुई।</p>",
                "no_search_term": "<div class='cludo-no-search-term'>कृपया एक खोज शब्द को प्रविष्ट करें</div>",
                "overlay_close_div": "ESC या",
                "overlay_close_button": "बंद करे",
                "load_more": "अधिक दिखाए",
                "poweredBy_title": "अपनी वेबसाइट की खोज पर नियंत्रण रखे - क्लुड़ो",
                "backToTop": "फिर से शीर्ष पर",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "बंद करे",
                "template_all_results": "सभी परिणाम",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "संबंधित खोजें",
                "suggested_searches_title": "सुझाई गई खोजें",
                "recent_searches_title": "हाल की खोजें",
                "template_nrm_use_another_search_word": "कोई दूसरा खोज शब्द आज़माएं",
                "template_nrm_try_to_search": "खोजने का प्रयास करें",
                "template_nrm_without_filters": "फिल्टर के बिना",
                "template_nrm_display": "प्रदर्शन",
                "template_nrm_all_results": "सभी परिणाम",
                "toggle_filters_label": "खोज फ़िल्टर टॉगल करें",
                "voice_search_title": "आवाज से खोजें",
                "search_filters": "फ़िल्टर खोजें",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "hu": {
                "did_you_mean": "Úgy értetted, hogy <a href='' aria-label='Úgy értetted, hogy {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "A keresésed a következõre: '<b>{{value}}</b>' ",
                "total_results": "<b>{{value}}</b> találatot adott",
                "total_result": "<b>{{value}}</b> találatot adott",
                "in_category": "  a következõ kategóriában: <b>{{value}}</b>",
                "and": " és",
                "searched_instead": "<br />Ehelyett <b>{{number}}</b> találat megjelenítése a következőre: <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Sajnáljuk, hiba történt.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Kérjük, adj meg egy keresõszót</div>",
                "overlay_close_div": "ESC vagy",
                "overlay_close_button": "becsuk",
                "load_more": "még több",
                "poweredBy_title": "Vedd át az irányítást a keresés felett a weboldaladon - Cludo",
                "backToTop": "Vissza a tetejére",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "becsuk",
                "template_all_results": "All Results",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Kapcsolódó keresések",
                "suggested_searches_title": "Javasolt keresések",
                "recent_searches_title": "Legutóbbi keresések",
                "template_nrm_use_another_search_word": "Próbálkozzon másik keresőszóval",
                "template_nrm_try_to_search": "Próbálj meg keresni",
                "template_nrm_without_filters": "szűrők nélkül",
                "template_nrm_display": "Kijelző",
                "template_nrm_all_results": "minden eredményt",
                "toggle_filters_label": "Kapcsolja be a keresési szűrőket",
                "voice_search_title": "Hangalapú keresés",
                "search_filters": "Keresési szűrők",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "is": {
                "did_you_mean": "Áttir þú við <a href='' aria-label='Áttir þú við {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Leit þín að '<b>{{value}}</b>' ",
                "total_results": " skilaði <b>{{value}}</b> niðurstöðum",
                "total_result": " skilaði <b>{{value}}</b> niðurstöðu",
                "in_category": "  í flokk <b>{{value}}</b>",
                "and": " og",
                "searched_instead": "<br />Sýnum í staðinn <b>{{number}}</b> niðurstöður fyrir <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Afsakið, við erum að upplifa óvænta villu. Vinsamlegast reyndu aftur síðar.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Vinsamlegast sláið inn leitarorð</div>",
                "overlay_close_div": "ESC eða",
                "overlay_close_button": "Loka",
                "load_more": "sýna meira",
                "poweredBy_title": "Stjórnaðu leitinni á þinni vefsíðu - Cludo",
                "backToTop": "Aftur upp",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Loka",
                "template_all_results": "Allar niðurstöður",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Tengdar leitir",
                "suggested_searches_title": "Tillaga að leit",
                "recent_searches_title": "Nýlegar leitir",
                "template_nrm_use_another_search_word": "Prófaðu annað leitarorð",
                "template_nrm_try_to_search": "Reyndu að leita",
                "template_nrm_without_filters": "án síu",
                "template_nrm_display": "Sýna",
                "template_nrm_all_results": "allar niðurstöður",
                "toggle_filters_label": "Skiptu um leitarsíur",
                "voice_search_title": "Leitaðu með rödd",
                "search_filters": "Leitarsíur",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "id": {
                "did_you_mean": "Maksud Anda <a href='' aria-label='Maksud Anda {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Pencarian Anda untuk '<b>{{value}}</b>' ",
                "total_results": " memberikan <b>{{value}}</b> hasil",
                "total_result": " memberikan <b>{{value}}</b> hasil",
                "in_category": " dalam kategori <b>{{value}}</b>",
                "and": "dan",
                "searched_instead": "<br />Menampilkan <b>{{number}}</b> hasil untuk <b>{{term}}</b> sebagai gantinya",
                "error": "<p style='color: red' class='cludo-error-message'>Maaf, terjadi kesalahan.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Harap masukkan kata pencarian</div>",
                "overlay_close_div": "Keluar atau",
                "overlay_close_button": "Menutup",
                "load_more": "tunjukkan lebih banyak",
                "poweredBy_title": "Ambil kendali pencarian di website Anda - Cludo",
                "backToTop": "Kembali ke atas",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Menutup",
                "template_all_results": "Semua hasil",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Pencarian terkait",
                "suggested_searches_title": "Pencarian yang disarankan",
                "recent_searches_title": "Pencarian terkini",
                "template_nrm_use_another_search_word": "Coba kata pencarian lain",
                "template_nrm_try_to_search": "Coba cari",
                "template_nrm_without_filters": "tanpa filter",
                "template_nrm_display": "Menampilkan",
                "template_nrm_all_results": "semua hasil",
                "toggle_filters_label": "Skiptu um leitarsíur",
                "voice_search_title": "Cari dengan suara",
                "search_filters": "Cari Filter",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "it": {
                "did_you_mean": "Intendi <a href='' aria-label='Intendi {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Hai cercato '<b>{{value}}</b>' ",
                "total_results": " ha fornito <b>{{value}}</b> risultati",
                "total_result": " ha fornito <b>{{value}}</b> risultato",
                "in_category": " nella categoria <b>{{value}}</b>",
                "and": "e",
                "searched_instead": "<br />Mostra invece <b>{{number}}</b> risultati per <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Spiacenti, si è verificato un errore.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Inserisci un termine di ricerca</div>",
                "overlay_close_div": "ESC o",
                "overlay_close_button": "Chiudere",
                "load_more": "visualizza altro",
                "poweredBy_title": "Prendi il controllo della ricarca sul tuo sito web - Cludo",
                "backToTop": "Torna all'inizio",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Chiudere",
                "template_all_results": "Tutti i risultati",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Ricerche correlate",
                "suggested_searches_title": "Ricerche suggerite",
                "recent_searches_title": "Ricerche recenti",
                "template_nrm_use_another_search_word": "Prova un'altra parola di ricerca",
                "template_nrm_try_to_search": "Prova a cercare",
                "template_nrm_without_filters": "senza filtri",
                "template_nrm_display": "Schermo",
                "template_nrm_all_results": "tutti i risultati",
                "toggle_filters_label": "Attiva/disattiva i filtri di ricerca",
                "voice_search_title": "Cerca a voce",
                "search_filters": "Filtri di ricerca",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "ko": {
                "did_you_mean": "Did you mean <a href='' aria-label='Did you mean {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Your search for '<b>{{value}}</b>' ",
                "total_results": "gave <b>{{value}}</b> results",
                "total_result": "gave <b>{{value}}</b> result",
                "in_category": " in the category <b>{{value}}</b>",
                "and": " and",
                "searched_instead": "<br />대신 <b>{{term}}</b>에 대한 <b>{{number}}</b>개의 결과 표시",
                "error": "<p style='color: red' class='cludo-error-message'>Sorry, an error occurred.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Please enter a search term</div>",
                "overlay_close_div": "ESC or",
                "overlay_close_button": "닫다",
                "load_more": "show more",
                "poweredBy_title": "Take control over the search on your website - Cludo",
                "backToTop": "Back to top",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "닫다",
                "template_all_results": "All Results",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Related Searches",
                "suggested_searches_title": "Suggested searches",
                "recent_searches_title": "Recent searches",
                "template_nrm_use_another_search_word": "Try another search word",
                "template_nrm_try_to_search": "Try to search",
                "template_nrm_without_filters": "without filters",
                "template_nrm_display": "Display",
                "template_nrm_all_results": "all results",
                "toggle_filters_label": "검색 필터 전환",
                "voice_search_title": "음성으로 검색",
                "search_filters": "검색 필터",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "lv": {
                "did_you_mean": "Vai domājāt <a href='' aria-label='Vai domājāt {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Jūs meklējāt '<b>{{value}}</b>' ",
                "total_results": " Vaicājumam ir <b>{{value}}</b> rezultāti",
                "total_result": " vaicājumam <b>{{value}}</b> rezultāts",
                "in_category": "  kategorijā <b>{{value}}</b>",
                "and": " un",
                "searched_instead": "<br />Tā vietā tiek rādīti <b>{{number}}</b> rezultāti vaicājumam <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Atvainojiet, radusies kļūda.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Lūdzu, ievadiet meklējamo terminu</div>",
                "overlay_close_div": "Nospiediet ESC vai",
                "overlay_close_button": "Aizvērt",
                "load_more": "rādīt vairāk",
                "poweredBy_title": "Kontrolēt meklēšanu mājas lapā - Cludo",
                "backToTop": "Atgriezties lapas sākumā",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Aizvērt",
                "template_all_results": "Visi rezultāti",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Saistītie meklējumi",
                "suggested_searches_title": "Ieteiktie meklējumi",
                "recent_searches_title": "Nesenie meklējumi",
                "template_nrm_use_another_search_word": "Izmēģiniet citu meklēšanas vārdu",
                "template_nrm_try_to_search": "Mēģiniet meklēt",
                "template_nrm_without_filters": "bez filtriem",
                "template_nrm_display": "Displejs",
                "template_nrm_all_results": "visi rezultāti",
                "toggle_filters_label": "Pārslēgt meklēšanas filtrus",
                "voice_search_title": "Meklēt ar balsi",
                "search_filters": "Meklēšanas filtri",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "lt": {
                "did_you_mean": "Ar turėjote omenyje <a href='' aria-label='Ar turėjote omenyje {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Ar ieškojote '<b>{{value}}</b>' ",
                "total_results": " pateikta <b>{{value}}</b> rezultatų",
                "total_result": " pateiktas <b>{{value}}</b> rezultatas",
                "in_category": " kategorijoje <b>{{value}}</b>",
                "and": " ir",
                "searched_instead": "<br />Vietoj to, pateikta <b>{{number}}</b> rezultatų žodžiui <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Apgailestaujame, tačiau įvyko klaida.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Įveskite ieškomą terminą</div>",
                "overlay_close_div": "ESC arba",
                "overlay_close_button": "Uždaryti",
                "load_more": "rodyti daugiau",
                "poweredBy_title": "Perimkite paieškos kontrolę savo internetinėje svetainėje - Cludo",
                "backToTop": "Grįžti į viršų",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Uždaryti",
                "template_all_results": "All Results",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Susijusios paieškos",
                "suggested_searches_title": "Siūlomos paieškos",
                "recent_searches_title": "Naujausios paieškos",
                "template_nrm_use_another_search_word": "Pabandykite kitą paieškos žodį",
                "template_nrm_try_to_search": "Pabandykite ieškoti",
                "template_nrm_without_filters": "be filtrų",
                "template_nrm_display": "Ekranas",
                "template_nrm_all_results": "visi rezultatai",
                "toggle_filters_label": "Perjungti paieškos filtru",
                "voice_search_title": "Ieškoti balsu",
                "search_filters": "Paieškos filtrai",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "no": {
                "did_you_mean": "Mente du <a href='' aria-label='Mente du {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Ditt søk etter '<b>{{value}}</b>' ",
                "total_results": " ga <b>{{value}}</b> resultater",
                "total_result": " ga <b>{{value}}</b> resultat",
                "in_category": "  i kategori <b>{{value}}</b>",
                "and": " og",
                "searched_instead": "<br />Viser <b>{{number}}</b> resultater for <b>{{term}}</b> i stedet",
                "error": "<p style='color: red' class='cludo-error-message'>Beklager, vi støtte på en uventet feil. Vennligst prøv igjen senere.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Skriv inn et søkeord</div>",
                "overlay_close_div": "ESC eller",
                "overlay_close_button": "Lukk",
                "load_more": "vis mer",
                "poweredBy_title": "Ta kontroll over søkene på nettstedet ditt - Cludo",
                "backToTop": "Tilbake til toppen",
                "search_input_label": "Søk",
                "search_button_text": "Søk",
                "overlay_close_button_title": "Lukk",
                "template_all_results": "Alle resultater",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Relaterte søk",
                "suggested_searches_title": "Foreslåtte søk",
                "recent_searches_title": "Nylige søk",
                "template_nrm_use_another_search_word": "Prøv et annet søkeord",
                "template_nrm_try_to_search": "Prøv å søke",
                "template_nrm_without_filters": "uten filtre",
                "template_nrm_display": "Vis",
                "template_nrm_all_results": "alle resultatene",
                "toggle_filters_label": "Slå på søkefiltre",
                "voice_search_title": "Søk med stemmen",
                "search_filters": "Søkefiltre",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "pl": {
                "did_you_mean": "Czy chodzi o <a href='' aria-label='Czy chodzi o {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Po zakończeniu wyszukiwania '<b>{{value}}</b>' ",
                "total_results": " otrzymano <b>{{value}}</b> wyników",
                "total_result": " otrzymano <b>{{value}}</b> wynik",
                "in_category": "  w kategorii <b>{{value}}</b>",
                "and": " oraz",
                "searched_instead": "<br />Zamiast tego wyszukaj <b>{{number}}</b> wyników dla  <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Wystąpił błąd.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Wprowadź pojęcie do wyszukiwania</div>",
                "overlay_close_div": "ESC lub",
                "overlay_close_button": "Zamknij",
                "load_more": "pokaż więcej",
                "poweredBy_title": "Wyszukuj na swojej stronie internetowej - Cludo",
                "backToTop": "Powrót do góry",
                "search_input_label": "Szukaj",
                "search_button_text": "Szukaj",
                "overlay_close_button_title": "Zamknij",
                "template_all_results": "Wszystkie wyniki",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Powiązane Wyszukiwania",
                "suggested_searches_title": "Sugerowane wyszukiwania",
                "recent_searches_title": "Ostatnie wyszukiwania",
                "template_nrm_use_another_search_word": "Spróbuj użyć innych słów kluczowych",
                "template_nrm_try_to_search": "Spróbuj szukać",
                "template_nrm_without_filters": "bez filtrów",
                "template_nrm_display": "Wyświetl",
                "template_nrm_all_results": "wszystkie wyniki",
                "toggle_filters_label": "Przełącz filtry wyszukiwania",
                "voice_search_title": "Wyszukiwanie głosowe",
                "search_filters": "Filtry wyszukiwania",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "pt": {
                "did_you_mean": "Queria dizer <a href='' aria-label='Queria dizer {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "A sua pesquisa por '<b>{{value}}</b>' ",
                "total_results": "obteve  <b>{{value}}</b> resultados",
                "total_result": "obteve  <b>{{value}}</b> resultado",
                "in_category": "  na categoria <b>{{value}}</b>",
                "and": " e",
                "searched_instead": "<br />Obteve <b>{{number}}</b> resultados para <b>{{term}}</b> como alternativa",
                "error": "<p style='color: red' class='cludo-error-message'>Lamentamos, ocorreu um erro.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Introduza um termo a procurar</div>",
                "overlay_close_div": "ESC ou",
                "overlay_close_button": "Fechar",
                "load_more": "mostrar mais",
                "poweredBy_title": "Assuma o controlo da pesquisa no seu website - Cludo",
                "backToTop": "Voltar ao topo",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Fechar",
                "template_all_results": "Todos os resultados",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Pesquisas relacionadas",
                "suggested_searches_title": "Pesquisas sugeridas",
                "recent_searches_title": "Pesquisas recentes",
                "template_nrm_use_another_search_word": "Tente outra palavra de pesquisa",
                "template_nrm_try_to_search": "Tente pesquisar",
                "template_nrm_without_filters": "sem filtros",
                "template_nrm_display": "Exibição",
                "template_nrm_all_results": "todos os resultados",
                "toggle_filters_label": "Mostrar/esconder filtros de pesquisa",
                "voice_search_title": "Pesquisa por voz",
                "search_filters": "Filtros de Pesquisa",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "ro": {
                "did_you_mean": "Vrei să spui <a href='' aria-label='Vrei să spui {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Căutarea termenului '<b>{{value}}</b>' ",
                "total_results": " a generat <b>{{value}}</b> de rezultate",
                "total_result": " a generat <b>{{value}}</b> rezultat",
                "in_category": "  în categoria <b>{{value}}</b>",
                "and": " și",
                "searched_instead": "<br /> Se afișează în schimb <b>{{number}}</b> rezultate pentru <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Ne pare rău, a apărut o eroare.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Introdu un nou termen pentru căutare</div>",
                "overlay_close_div": "ESC sau",
                "overlay_close_button": "Închide",
                "load_more": "arată mai multe",
                "poweredBy_title": "Preia controlul asupra căutării pe pagina ta web - Cludo",
                "backToTop": "Înapoi sus",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Închide",
                "template_all_results": "Toate rezultatele",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Căutări asemanatoare",
                "suggested_searches_title": "Căutări sugerate",
                "recent_searches_title": "Căutări recente",
                "template_nrm_use_another_search_word": "Încercați un alt cuvânt de căutare",
                "template_nrm_try_to_search": "Încercați să căutați",
                "template_nrm_without_filters": "fara filtre",
                "template_nrm_display": "Afişa",
                "template_nrm_all_results": "toate rezultatele",
                "toggle_filters_label": "Arată/ascunde filtrele de căutare",
                "voice_search_title": "Faceți o căutare vocală",
                "search_filters": "Filtre de căutare",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "ru": {
                "did_you_mean": "Вы имели в виду <a href='' aria-label='Вы имели в виду {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Поиск '<b>{{value}}</b>' ",
                "total_results": "дал <b>{{value}}</b> результатов",
                "total_result": "дал <b>{{value}}</b> результат",
                "in_category": "в категории <b>{{value}}</b>",
                "and": "и",
                "searched_instead": "<br />Вместо этого показаны <b>{{number}}</b> результаты для <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Извините, возникла ошибка.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Введите искомый термин</div>",
                "overlay_close_div": "ESC или",
                "overlay_close_button": "Закрывать",
                "load_more": "показать больше",
                "poweredBy_title": "Управляйте поиском на своем сайте - Cludo",
                "backToTop": "Наверх",
                "search_input_label": "Поиск",
                "search_button_text": "Поиск",
                "overlay_close_button_title": "Закрывать",
                "template_all_results": "Все результаты",
                "template_suggestions": "Предложения",
                "template_search_results": "Результаты поиска",
                "template_autocomplete_hint": "Результаты автодополнения доступны. Используйте стрелки вверх и вниз для просмотра и выбора.",
                "related_searches_title": "Похожие Запросы",
                "suggested_searches_title": "Предлагаемые поиски",
                "recent_searches_title": "Недавние поиски",
                "template_nrm_use_another_search_word": "Попробуйте другое поисковое слово",
                "template_nrm_try_to_search": "Попробуйте поискать",
                "template_nrm_without_filters": "без фильтров",
                "template_nrm_display": "Отображать",
                "template_nrm_all_results": "все результаты",
                "toggle_filters_label": "Переключить поисковые фильтры",
                "voice_search_title": "Голосовой поиск",
                "search_filters": "Фильтры поиска",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "sr": {
                "did_you_mean": "Da li ste mislili <a href='' aria-label='Da li ste mislili {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Vaša pretraga za '<b>{{value}}</b>' ",
                "total_results": " dala je <b>{{value}}</b> rezultata",
                "total_result": " dala je <b>{{value}}</b> rezultat",
                "in_category": "  u kategoriji <b>{{value}}</b>",
                "and": " i",
                "searched_instead": "<br />Umjesto toga prikazuje se <b>{{number}}</b> rezultata za <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Žao nam je, došlo je do greške.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Molimo unesite reč za pretraživanje</div>",
                "overlay_close_div": "ESC ili",
                "overlay_close_button": "Zatvori",
                "load_more": "prikaži još",
                "poweredBy_title": "Preuzmite kontrolu nad pretragom na Vašem veb-sajtu - Cludo",
                "backToTop": "Nazad do vrha",
                "search_input_label": "Pretraga",
                "search_button_text": "Pronađi",
                "overlay_close_button_title": "Zatvori",
                "template_all_results": "Svi resultati",
                "template_suggestions": "Sugestije",
                "template_search_results": "Rezultati pretrage",
                "template_autocomplete_hint": "Rezultati automatskog dovršavanja su dostupni. Koristite strelice gore/dole za pregled i 'Enter' da biste izabrali.",
                "related_searches_title": "Srodne pretrage",
                "suggested_searches_title": "Predložena pretraživanja",
                "recent_searches_title": "Nedavna pretraživanja",
                "template_nrm_use_another_search_word": "Isprobajte drugu reč za pretragu",
                "template_nrm_try_to_search": "Pokušaj da pretražuješ",
                "template_nrm_without_filters": "bez filtera",
                "template_nrm_display": "Prikazivanje",
                "template_nrm_all_results": "svi rezultati",
                "toggle_filters_label": "Укључите филтере за претрагу",
                "voice_search_title": "Претражујте гласом",
                "search_filters": "Филтери за претрагу",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "es": {
                "did_you_mean": "¿Quiso decir <a href='' aria-label='¿Quiso decir {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Su búsqueda de '<b>{{value}}</b>' ",
                "total_results": " ha producido <b>{{value}}</b> resultados",
                "total_result": " ha producido <b>{{value}}</b> resultado",
                "in_category": "  en la categoría <b>{{value}}</b>",
                "and": " y",
                "searched_instead": "<br />Mostrando <b>{{number}}</b> resultados para <b>{{term}}</b> en su lugar",
                "error": "<p style='color: red' class='cludo-error-message'>Lo sentimos, ha ocurrido un error.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Por favor, introduzca un término de búsqueda</div>",
                "overlay_close_div": "ESC o",
                "overlay_close_button": "Cerrar",
                "load_more": "mostrar más",
                "poweredBy_title": "Tome el control de las búsquedas en su sitio web - Cludo",
                "backToTop": "Volver al inicio",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Cerrar",
                "template_all_results": "Todos los resultados",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Búsquedas relacionadas",
                "suggested_searches_title": "Búsquedas sugeridas",
                "recent_searches_title": "Búsquedas recientes",
                "template_nrm_use_another_search_word": "Intenta buscar otra palabra",
                "template_nrm_try_to_search": "Intenta buscar",
                "template_nrm_without_filters": "sin filtros",
                "template_nrm_display": "Muestra",
                "template_nrm_all_results": "todos los resultados",
                "toggle_filters_label": "Mostrar/ocultar filtros de búsqueda",
                "voice_search_title": "Búsqueda por voz",
                "search_filters": "Filtros de búsqueda",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "th": {
                "did_you_mean": "คุณหมายความว่า <a href='' aria-label='คุณหมายความว่า {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "การค้นหาของคุณสำหรับ '<b>{{value}}</b>' ",
                "total_results": " ให้ <b>{{value}}</b> ผลการค้นหา",
                "total_result": " ให้ <b>{{value}}</b> ผลการค้นหา",
                "in_category": "  ในหมวดหมู่ <b>{{value}}</b>",
                "and": " และ",
                "searched_instead": "<br />  แทน เพื่อดูผลการค้นหาจำนวน <b>{{number}}</b> รายการ ค้นหาคำว่า <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>ขออภัยมีข้อผิดพลาดเกิดขึ้น</p>",
                "no_search_term": "<div class='cludo-no-search-term'>กรุณากรอกคำที่ต้องการค้นหา</div>",
                "overlay_close_div": "ESC หรือ",
                "overlay_close_button": "ปิด",
                "load_more": "แสดงเพิ่มเติม",
                "poweredBy_title": "ควบคุมการค้นหาบนเว็บไซต์ของคุณ - Cludo",
                "backToTop": "กลับไปที่ด้านบน",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "ปิด",
                "template_all_results": "ผลลัพธ์ทั้งหมด",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "การค้นหาที่เกี่ยวข้อง",
                "suggested_searches_title": "การค้นหาที่แนะนำ",
                "recent_searches_title": "ผลค้นหาล่าสุด",
                "template_nrm_use_another_search_word": "ลองคำค้นหาอื่น",
                "template_nrm_try_to_search": "ลองค้นหาดู",
                "template_nrm_without_filters": "ไม่มีตัวกรอง",
                "template_nrm_display": "แสดง",
                "template_nrm_all_results": "ผลลัพธ์ทั้งหมด",
                "toggle_filters_label": "สลับตัวกรองการค้นหา",
                "voice_search_title": "ค้นหาด้วยเสียง",
                "search_filters": "ตัวกรองการค้นหา",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "tr": {
                "did_you_mean": "Şunu mu demek istediniz <a href='' aria-label='Şunu mu demek istediniz {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "'<b>{{value}}</b>' için yaptığınız arama",
                "total_results": "<b>{{value}}</b> sonuç verdi",
                "total_result": "<b>{{value}}</b> sonuç verdi",
                "in_category": "<b>{{value}}</b> kategorisinde",
                "and": " ve",
                "searched_instead": "<br />Bunun yerine <b>{{number}}</b> için <b>{{term}}</b> sonuçları gösterilir",
                "error": "<p style='color: red' class='cludo-error-message'>Üzgünüz, bir hata meydana geldi.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Lütfen bir arama terimi girin</div>",
                "overlay_close_div": "ESC veya",
                "overlay_close_button": "Kapat",
                "load_more": "daha fazla göster",
                "poweredBy_title": "Web sitenizdeki aramaların kontrolünü elinize alın - Cludo",
                "backToTop": "Başa dön",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Kapat",
                "template_all_results": "Tüm sonuçlar",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Ilgili aramalar",
                "suggested_searches_title": "Önerilen aramalar",
                "recent_searches_title": "Son aramalar",
                "template_nrm_use_another_search_word": "Başka bir arama sözcüğü deneyin",
                "template_nrm_try_to_search": "Aramayı dene",
                "template_nrm_without_filters": "filtreler olmadan",
                "template_nrm_display": "Görüntülemek",
                "template_nrm_all_results": "tüm sonuçlar",
                "toggle_filters_label": "Arama filtrelerini aç/kapat",
                "voice_search_title": "sesle arama",
                "search_filters": "Arama Filtreleri",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "uk": {
                "did_you_mean": "Ви мали на увазі <a href='' aria-label='Ви мали на увазі {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Ваш пошук '<b>{{value}}</b>' ",
                "total_results": "дав <b>{{value}}</b> результатів",
                "total_result": "дав <b>{{value}}</b> pезультат",
                "in_category": "у категорії <b>{{value}}</b>",
                "and": " і",
                "searched_instead": "<br />Натомість відображаються результати <b>{{number}}</b> для <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>На жаль, сталася помилка.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Будь ласка, введіть слово для пошуку</div>",
                "overlay_close_div": "ESC або",
                "overlay_close_button": "Закрити",
                "load_more": "показати більше",
                "poweredBy_title": "Візьміть під контроль пошук на Вашому веб-сайті - Cludo",
                "backToTop": "Повернутись до початку",
                "search_input_label": "Пошук",
                "search_button_text": "Пошук",
                "overlay_close_button_title": "Закрити",
                "template_all_results": "Всі результати",
                "template_suggestions": "Пропозиції",
                "template_search_results": "Результати пошуку",
                "template_autocomplete_hint": "Результати автодоповнення доступні. Використовуйте стрілки вгору і вниз для перегляду і вибору.",
                "related_searches_title": "Пов'язані пошукові запити",
                "suggested_searches_title": "Пропоновані пошукові запити",
                "recent_searches_title": "Останні пошукові запити",
                "template_nrm_use_another_search_word": "Спробуйте інше слово для пошуку",
                "template_nrm_try_to_search": "Спробуйте пошукати",
                "template_nrm_without_filters": "без фільтрів",
                "template_nrm_display": "Дисплей",
                "template_nrm_all_results": "всі результати",
                "toggle_filters_label": "Увімкнути фільтри пошуку",
                "voice_search_title": "Голосовий пошук",
                "search_filters": "Фільтри пошуку",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "vi": {
                "did_you_mean": "Có phải bạn muốn tìm <a href='' aria-label='Có phải bạn muốn tìm {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "Tìm kiếm '<b>{{value}}</b>' ",
                "total_results": "có <b>{{value}}</b> kết quả",
                "total_result": "có <b>{{value}}</b> kết quả",
                "in_category": "trong thể loại <b>{{value}}</b>",
                "and": " và",
                "searched_instead": "<br />Thay vào đó, hiển thị kết quả <b>{{number}}</b> cho <b>{{term}}</b>",
                "error": "<p style='color: red' class='cludo-error-message'>Rất tiếc, đã xảy ra lỗi.</p>",
                "no_search_term": "<div class='cludo-no-search-term'>Vui lòng nhập một từ khóa tìm kiếm</div>",
                "overlay_close_div": "ESC hoặc",
                "overlay_close_button": "Thoát",
                "load_more": "hiển thị thêm",
                "poweredBy_title": "Kiểm soát tìm kiếm trên trang web của bạn - Cludo",
                "backToTop": "Quay lại đầu trang",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Thoát",
                "template_all_results": "Tất cả kết quả",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "Tìm kiếm liên quan",
                "suggested_searches_title": "Tìm kiếm được Đề xuất",
                "recent_searches_title": "Tìm kiếm gần đây",
                "template_nrm_use_another_search_word": "Hãy thử một từ tìm kiếm khác",
                "template_nrm_try_to_search": "Cố gắng tìm kiếm",
                "template_nrm_without_filters": "không có bộ lọc",
                "template_nrm_display": "Trưng bày",
                "template_nrm_all_results": "tất cả kết quả",
                "toggle_filters_label": "Chuyển đổi bộ lọc tìm kiếm",
                "voice_search_title": "Tìm kiếm bằng giọng nói",
                "search_filters": "Bộ lọc tìm kiếm",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            },
            "jp": {
                "did_you_mean": "もしかして <a href='' aria-label='Did you mean {{value}}'><b>{{value}}</b></a>?",
                "your_search_on": "'<b>{{value}}</b>' で検索し ",
                "total_results": "<b>{{value}}</b> 件の結果がありました。",
                "total_result": "<b>{{value}}</b> 件の結果がありました。",
                "in_category": " カテゴリ <b>{{value}}</b>",
                "and": " そして",
                "searched_instead": "<br />代わりに <b>{{number}}</b> の <b>{{term}}</b> の結果を表示する",
                "error": "<p style='color: red' class='cludo-error-message'>申し訳ありませんが、エラーが発生しました</p>",
                "no_search_term": "<div class='cludo-no-search-term'>検索語を入力してください</div>",
                "overlay_close_div": "ESC or",
                "overlay_close_button": "Thoát",
                "load_more": "もっと見せる",
                "poweredBy_title": "Take control over the search on your website - Cludo",
                "backToTop": "トップに戻る",
                "search_input_label": "Search",
                "search_button_text": "Search",
                "overlay_close_button_title": "Thoát",
                "template_all_results": "すべての結果",
                "template_suggestions": "Suggestions",
                "template_search_results": "Search Results",
                "template_autocomplete_hint": "Autocomplete suggestions are available. Use up and down arrows to review and enter to select.",
                "related_searches_title": "関連検索",
                "suggested_searches_title": "提案された検索",
                "recent_searches_title": "最近の検索",
                "template_nrm_use_another_search_word": "別の検索語を試す",
                "template_nrm_try_to_search": "検索してみてください",
                "template_nrm_without_filters": "フィルタなし",
                "template_nrm_display": "画面",
                "template_nrm_all_results": "すべての結果",
                "toggle_filters_label": "検索フィルターを切り替えます",
                "voice_search_title": "音声で検索",
                "search_filters": "検索フィルター",
                "loading_results": "Loading search results",
                "general_page": "Page",
                "next_page": "Next page",
                "prev_page": "Previous page",
                "general_relevance": "Relevance"
            }
        };
    }
    /** Looks up translation by translation id and language and, if applicable, will replace {{value}} with replace variable */
    TranslateProvider.prototype.translate = function (translationId, replace, languageToUse) {
        if (languageToUse === undefined) {
            languageToUse = this.language;
        }
        if (!this.translations[languageToUse] || !this.translations[languageToUse][translationId]) {
            return translationId;
        }
        var r = typeof replace !== 'undefined' ? replace : '';
        return this.translations[languageToUse][translationId].replace(new RegExp('{{value}}', 'g'), r);
    };
    /** Looks up translation by translation id and language and, if applicable, will replace {{value}} with replace variable */
    TranslateProvider.prototype.translateWithParameters = function (translationId, replace, languageToUse) {
        if (languageToUse === undefined) {
            languageToUse = this.language;
        }
        if (replace === undefined) {
            replace = {};
        }
        if (!this.translations[languageToUse] || !this.translations[languageToUse][translationId]) {
            return translationId;
        }
        if (Object.keys(replace).length > 0) {
            return Object.keys(replace).reduce(function (interpolated, key) {
                if (!interpolated || !key) {
                    return '';
                }
                return interpolated.replace(new RegExp('{{\\s*' + key + '\\s*}}', 'g'), replace[key]);
            }, this.translations[languageToUse][translationId]);
        }
        else {
            this.translations[languageToUse][translationId];
        }
    };
    /** Translates strings from templating system of format {{some_variable}} to be passed to translate function */
    TranslateProvider.prototype.translateTokens = function (stringToTranslate) {
        var _this = this;
        if (stringToTranslate) {
            return stringToTranslate.replace(/{{(.*?)}}/g, function (token, tokenValue) {
                return _this.translate(tokenValue);
            });
        }
        else {
            return stringToTranslate;
        }
    };
    return TranslateProvider;
}());


;// CONCATENATED MODULE: ./src/storage-service.ts
var _a;
var StorageKey;
(function (StorageKey) {
    StorageKey["SessionId"] = "cludoSessionId";
    StorageKey["CookieConsent"] = "cludoCachedCookieConsent";
    StorageKey["RecentSearches"] = "recentSearches";
    StorageKey["Traits"] = "cludoTraits";
    StorageKey["Conversations"] = "qaConversations";
})(StorageKey || (StorageKey = {}));
// Keyed objects store data on a per-instance basis, while global objects do not
var StorageKeyContext;
(function (StorageKeyContext) {
    StorageKeyContext["keyed"] = "keyed";
    StorageKeyContext["global"] = "global";
})(StorageKeyContext || (StorageKeyContext = {}));
// Map the different keys to the kind of context they store
var StorageKeyContextMap = (_a = {},
    _a[StorageKey.CookieConsent] = StorageKeyContext.global,
    _a[StorageKey.Traits] = StorageKeyContext.global,
    _a[StorageKey.SessionId] = StorageKeyContext.keyed,
    _a[StorageKey.RecentSearches] = StorageKeyContext.keyed,
    _a[StorageKey.Conversations] = StorageKeyContext.keyed,
    _a);
var StorageType;
(function (StorageType) {
    StorageType["NoOp"] = "NoOp";
    StorageType["Memory"] = "Memory";
    StorageType["LocalStorage"] = "LocalStorage";
})(StorageType || (StorageType = {}));
var TrackingStatus;
(function (TrackingStatus) {
    TrackingStatus[TrackingStatus["Unknown"] = -1] = "Unknown";
    TrackingStatus[TrackingStatus["Disallowed"] = 0] = "Disallowed";
    TrackingStatus[TrackingStatus["Allowed"] = 1] = "Allowed";
})(TrackingStatus || (TrackingStatus = {}));
/** MemoryStorage used when localStorage is disabled in the browser */
var MemoryStorage = /** @class */ (function () {
    function MemoryStorage() {
        this.storage = {};
    }
    Object.defineProperty(MemoryStorage.prototype, "length", {
        get: function () {
            return Object.keys(this.storage).length;
        },
        enumerable: false,
        configurable: true
    });
    MemoryStorage.prototype.getItem = function (key) {
        return this.storage[key];
    };
    MemoryStorage.prototype.setItem = function (key, value) {
        this.storage[key] = value;
    };
    MemoryStorage.prototype.clear = function () {
        this.storage = {};
    };
    MemoryStorage.prototype.removeItem = function (key) {
        delete this.storage[key];
    };
    return MemoryStorage;
}());
/** NoOpStorage ("No Operation" Storage) is used when customer/user explicitly disallows tracking. Its `storage` can refer to localStorage or memory storage */
var NoOpStorage = /** @class */ (function () {
    function NoOpStorage() {
        if (StorageService.isLocalStorageAvailable()) {
            this.storage = window.localStorage;
        }
        else {
            this.storage = new MemoryStorage();
        }
    }
    Object.defineProperty(NoOpStorage.prototype, "length", {
        get: function () {
            return Object.keys(this.storage).length;
        },
        enumerable: false,
        configurable: true
    });
    /** For NoOp storage, we should only store the cookie consent value */
    NoOpStorage.prototype.setItem = function (key, value) {
        if (key !== StorageKey.CookieConsent) {
            console.warn("User/Customer settings prevented session storage: Key: ".concat(key, ", Value: ").concat(value));
        }
        else {
            this.storage.setItem(key, value);
        }
    };
    /** For NoOp storage, we should only return the cookie consent value */
    NoOpStorage.prototype.getItem = function (key) {
        if (key !== StorageKey.CookieConsent) {
            console.warn("User/Customer settings prevented session storage: Key: ".concat(key));
            return null;
        }
        else {
            return this.storage.getItem(key);
        }
    };
    NoOpStorage.prototype.clear = function () {
        this.storage.clear();
    };
    NoOpStorage.prototype.removeItem = function (key) {
        this.storage.removeItem(key);
    };
    return NoOpStorage;
}());
var StorageService = /** @class */ (function () {
    /**
     * @param prefix Defaults to "cludo", but can be overridden to allow for multiple instances of Cludo on the same page
     * @param instanceId A unique identifier for this instance, either the engine ID or experience ID
     */
    function StorageService(prefix, instanceId) {
        this.instanceKey = "".concat(prefix, "-").concat(instanceId);
        this.initializeStorage();
    }
    /** Determines if local storage is available in the browser */
    StorageService.isLocalStorageAvailable = function () {
        var mod = 'cludojs';
        try {
            localStorage.setItem(mod, mod);
            localStorage.removeItem(mod);
            return true;
        }
        catch (e) {
            return false;
        }
    };
    StorageService.prototype.getTrackingStatus = function () {
        var explicitCookieConsentStoredValue = this.getItem(StorageKey.CookieConsent);
        try {
            if (explicitCookieConsentStoredValue === null || explicitCookieConsentStoredValue === undefined) {
                // do nothing as we don't have anything to initialize
                return TrackingStatus.Unknown;
            }
            if (explicitCookieConsentStoredValue === false) {
                return TrackingStatus.Disallowed;
            }
            else {
                return TrackingStatus.Allowed;
            }
        }
        catch (_a) {
            return TrackingStatus.Disallowed;
        }
    };
    StorageService.prototype.enableTrackingForUser = function () {
        this.initializeStorage(true);
        this.setItem(StorageKey.CookieConsent, true);
    };
    StorageService.prototype.disableTrackingForUser = function () {
        // If user rejects cookie consent, clear storage
        this.clear();
        // Switch to NoOp storage
        this.initializeStorage(false);
        // Set flag for query log that the log is for an untracked sesion
        this.setItem(StorageKey.CookieConsent, false);
    };
    /** Switch to NoOp storage but don't cache CookieConsent value */
    StorageService.prototype.disableTrackingForCustomer = function () {
        this.clear();
        this.initializeStorage(false);
    };
    StorageService.prototype.initializeStorage = function (allowTracking) {
        if (!allowTracking) {
            this.storage = new NoOpStorage();
            if (allowTracking === undefined) {
                allowTracking = this.getTrackingStatus() !== TrackingStatus.Disallowed;
            }
        }
        if (allowTracking) {
            if (StorageService.isLocalStorageAvailable()) {
                this.initializeStorageByType(StorageType.LocalStorage);
            }
            else {
                this.initializeStorageByType(StorageType.Memory);
            }
        }
    };
    StorageService.prototype.initializeStorageByType = function (storageType) {
        try {
            switch (storageType) {
                case StorageType.NoOp:
                    this.storage = new NoOpStorage();
                    break;
                case StorageType.Memory:
                    this.storage = new MemoryStorage();
                    break;
                case StorageType.LocalStorage:
                    this.storage = window.localStorage;
                    break;
            }
        }
        catch (e) {
            console.warn(e);
        }
    };
    /** Gets a value from storage **/
    StorageService.prototype.getItem = function (key, defaultValue) {
        if (defaultValue === void 0) { defaultValue = null; }
        if (!this.storage) {
            return null;
        }
        var rawValue = this.storage.getItem(key);
        // ensure rawValue is the correct format
        rawValue = this.tryConvertValue(key, rawValue);
        if (StorageKeyContextMap[key] === StorageKeyContext.keyed) {
            return this.getKeyedObject(rawValue, defaultValue);
        }
        else {
            return this.getGlobalObject(rawValue, defaultValue);
        }
    };
    /** Get the value for the current instance out of the stored dictionary */
    StorageService.prototype.getKeyedObject = function (rawValue, defaultValue) {
        if (defaultValue === void 0) { defaultValue = null; }
        if (!rawValue) {
            return defaultValue;
        }
        var typedDictionary = {};
        try {
            typedDictionary = JSON.parse(rawValue) || {};
        }
        catch (_a) {
            typedDictionary = {};
        }
        var typedValue = typedDictionary[this.instanceKey] || defaultValue;
        return typedValue;
    };
    /** Stores the converted version of the value */
    StorageService.prototype.tryConvertValue = function (key, rawValue) {
        switch (key) {
            case StorageKey.SessionId:
                return this.convertSessionId(rawValue);
            case StorageKey.RecentSearches:
                return this.convertRecentSearches(rawValue);
            default:
                return rawValue;
        }
    };
    /** Converts the stored value to the correct format and return the correct raw stored value */
    StorageService.prototype.convertSessionId = function (rawValue) {
        var _a;
        if (!rawValue) {
            return null;
        }
        try {
            JSON.parse(rawValue); // If rawValue isn't an encoded object, this will throw an error
        }
        catch (_b) {
            // check for raw string session id (GUID -- 32 characters long, no dashes, all lowercase and hexadecimal)
            var isSessionId = rawValue.length === 32 && rawValue.indexOf('-') === -1 && rawValue.match(/^[0-9a-f]+$/);
            if (isSessionId) {
                // update to new format
                var storedSessionStart = this.storage.getItem('cludoSessionIdStart');
                this.storage.setItem(StorageKey.SessionId, JSON.stringify((_a = {},
                    _a[this.instanceKey] = { sessionId: rawValue, sessionStart: storedSessionStart || new Date().toString() },
                    _a)));
                return this.storage.getItem(StorageKey.SessionId);
            }
        }
        return rawValue;
    };
    /** Converts the stored value to the correct format and return the correct raw stored value */
    StorageService.prototype.convertRecentSearches = function (rawValue) {
        var _a, _b;
        if (!rawValue) {
            return null;
        }
        try {
            var parsedValue = JSON.parse(rawValue);
            // old format -- array of strings
            if (Array.isArray(parsedValue)) {
                // update to new format
                this.storage.setItem(StorageKey.RecentSearches, JSON.stringify((_a = {},
                    _a[this.instanceKey] = parsedValue,
                    _a)));
                return this.storage.getItem(StorageKey.RecentSearches);
            }
        }
        catch (_c) {
            this.storage.setItem(StorageKey.RecentSearches, JSON.stringify((_b = {},
                _b[this.instanceKey] = [],
                _b)));
            return this.storage.getItem(StorageKey.RecentSearches);
        }
        return rawValue;
    };
    /** Get the value from global storage (not stored in a dictionary) */
    StorageService.prototype.getGlobalObject = function (rawValue, defaultValue) {
        if (defaultValue === void 0) { defaultValue = null; }
        if (!rawValue) {
            return defaultValue;
        }
        var typedValue = defaultValue;
        try {
            typedValue = JSON.parse(rawValue);
            typedValue = (typedValue !== null || typedValue !== undefined) ? typedValue : defaultValue;
        }
        catch (_a) {
            typedValue = defaultValue;
        }
        return typedValue;
    };
    /** Sets the item in storage (either for a keyed storage dictionary, or for globally stored values) */
    StorageService.prototype.setItem = function (key, value) {
        if (!this.storage) {
            return;
        }
        if (StorageKeyContextMap[key] === StorageKeyContext.keyed) {
            try {
                var storedDictionary = JSON.parse(this.storage.getItem(key)) || {};
                storedDictionary[this.instanceKey] = value;
                this.storage.setItem(key, JSON.stringify(storedDictionary));
            }
            catch (_a) {
                // If we can't parse the stored value, we'll just overwrite it
                var storedDictionary = {};
                storedDictionary[this.instanceKey] = value;
                this.storage.setItem(key, JSON.stringify(storedDictionary));
            }
        }
        else {
            this.storage.setItem(key, JSON.stringify(value));
        }
    };
    /** Clears storage values */
    StorageService.prototype.clear = function () {
        var _this = this;
        if (!this.storage) {
            return;
        }
        // Clear only stored values that CludoJS controls
        Object.values(StorageKey).forEach(function (key) {
            _this.storage.removeItem(key);
        });
    };
    StorageService.prototype.getLength = function () {
        if (!this.storage) {
            return null;
        }
        return this.storage.length;
    };
    // TODO: Update to work with keyed and global objects -- not a big issue now because we never call into this
    StorageService.prototype.removeItem = function (key) {
        if (!this.storage) {
            return;
        }
        this.storage.removeItem(key);
    };
    return StorageService;
}());


;// CONCATENATED MODULE: ./src/types/cludo-types.ts
var allowedUrlListDelimiters = [',', '|', '~', '!'];

;// CONCATENATED MODULE: ./src/types/http-types.ts
var XMLRequestState;
(function (XMLRequestState) {
    XMLRequestState[XMLRequestState["UNSENT"] = 0] = "UNSENT";
    XMLRequestState[XMLRequestState["OPENED"] = 1] = "OPENED";
    XMLRequestState[XMLRequestState["HEADERS_RECEIVED"] = 2] = "HEADERS_RECEIVED";
    XMLRequestState[XMLRequestState["LOADING"] = 3] = "LOADING";
    XMLRequestState[XMLRequestState["DONE"] = 4] = "DONE";
})(XMLRequestState || (XMLRequestState = {}));
var XMLResponseStatus;
(function (XMLResponseStatus) {
    XMLResponseStatus[XMLResponseStatus["SUCCESS"] = 200] = "SUCCESS";
    XMLResponseStatus[XMLResponseStatus["UNAUTHORIZE"] = 401] = "UNAUTHORIZE";
    XMLResponseStatus[XMLResponseStatus["NOT_FOUND"] = 404] = "NOT_FOUND";
    XMLResponseStatus[XMLResponseStatus["SERVER_ERROR"] = 500] = "SERVER_ERROR";
})(XMLResponseStatus || (XMLResponseStatus = {}));

;// CONCATENATED MODULE: ./src/http-service.ts
var __assign = (undefined && undefined.__assign) || function () {
    __assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var __awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};


/** Static class for performing HTTP Requests */
var HttpService = /** @class */ (function () {
    function HttpService() {
    }
    /**
     * Get Authorization key for use with intranet requests
     *
     * @param customerId
     * @param instanceId - Either engineId or experienceId
     * @param siteKey
     * */
    HttpService.getAuthorizationKey = function (customerId, instanceId, siteKey) {
        var key = customerId + ":" + instanceId + ":" + siteKey;
        var base64key = window.btoa(key);
        return base64key;
    };
    /** Builds a url by flattening the parameters object and adding it to the passed url */
    HttpService.buildUrl = function (url, parameters) {
        var urlWithParams = url;
        var flattenPrameters = Helpers.flatten(parameters);
        var isFirst = true;
        for (var key in flattenPrameters) {
            var fragment = flattenPrameters[key];
            if (fragment !== undefined) {
                urlWithParams += (isFirst ? "?" : "&") + key + "=";
                // We add a value only if it has a value. 
                // Otherwise, we leave the parameter without a value.
                // This is done for backwards compatibility.
                if (fragment !== null) {
                    var value = encodeURIComponent(fragment);
                    urlWithParams = urlWithParams + value;
                }
            }
            isFirst = false;
        }
        return urlWithParams;
    };
    /** Determine the API url based on the customer ID -- IDs greater than 10000000 refer to US customers */
    HttpService.getBaseUrlForCustomer = function (customerId, version) {
        if (version === void 0) { version = 3; }
        return (customerId >= 10000000) ? "https://api-us1.cludo.com/api/v".concat(version) : "https://api.cludo.com/api/v".concat(version);
    };
    // FUTURE: Remove this method when we have migrated to fetch
    /** Performs a POST request to the provided url and returns a promise */
    HttpService.post = function (url, body, options) {
        return new Promise(function (resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.open("POST", url, true);
            xhr.onreadystatechange = function () {
                if (xhr.readyState === XMLRequestState.DONE) {
                    if (xhr.status === XMLResponseStatus.SUCCESS) {
                        resolve(xhr.responseText);
                    }
                    else {
                        reject();
                    }
                }
            };
            // Attach headers
            xhr.setRequestHeader("Content-type", options.contentType + ";charset=UTF-8");
            xhr.setRequestHeader("Accept", options.contentType);
            if (!options.isIntranet) {
                xhr.setRequestHeader("Authorization", "SiteKey " + options.authorizationKey);
            }
            else if (options.customHeaders) {
                Object.entries(options.customHeaders).forEach(function (header) {
                    xhr.setRequestHeader(header[0], header[1]);
                });
            }
            xhr.send(body);
        });
    };
    // FUTURE: Remove this method when we have migrated to fetch
    /** Performs a GET request to the provided url and returns a promise */
    HttpService.get = function (url, options) {
        return new Promise(function (resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", url, true);
            xhr.onreadystatechange = function () {
                if (xhr.readyState === XMLRequestState.DONE) {
                    if (xhr.status === XMLResponseStatus.SUCCESS) {
                        resolve(xhr.responseText);
                    }
                    else {
                        reject();
                    }
                }
            };
            // Attach headers
            xhr.setRequestHeader("Content-type", options.contentType + ";charset=UTF-8");
            xhr.setRequestHeader("Accept", options.contentType);
            if (!options.isIntranet) {
                xhr.setRequestHeader("Authorization", "SiteKey " + options.authorizationKey);
            }
            else if (options.customHeaders) {
                Object.entries(options.customHeaders).forEach(function (header) {
                    xhr.setRequestHeader(header[0], header[1]);
                });
            }
            xhr.send();
        });
    };
    /** Performs a GET request using the fetch API to the provided url and returns a promise */
    HttpService.getWithFetch = function (url, options) {
        return __awaiter(this, void 0, void 0, function () {
            var responseObject, response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, fetch(url, {
                            method: 'GET',
                            headers: HttpService.buildHeadersFromOptions(options),
                            signal: options.abortSignal
                        })];
                    case 1:
                        responseObject = _a.sent();
                        if (!responseObject.ok) {
                            throw (new Error(responseObject.statusText));
                        }
                        return [4 /*yield*/, responseObject.text()];
                    case 2:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        });
    };
    /** Performs a POST request using the fetch API to the provided url and returns a promise */
    HttpService.postWithFetch = function (url, body, options) {
        return __awaiter(this, void 0, void 0, function () {
            var responseObject, response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, fetch(url, {
                            method: 'POST',
                            headers: HttpService.buildHeadersFromOptions(options),
                            body: JSON.stringify(body),
                            signal: options.abortSignal
                        })];
                    case 1:
                        responseObject = _a.sent();
                        if (!responseObject.ok) {
                            throw (new Error(responseObject.statusText));
                        }
                        return [4 /*yield*/, responseObject.text()];
                    case 2:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        });
    };
    HttpService.buildHeadersFromOptions = function (options) {
        var headers = {
            'Content-Type': options.contentType + ";charset=UTF-8",
            'Accept': options.contentType,
        };
        if (!options.isIntranet) {
            headers['Authorization'] = 'SiteKey ' + options.authorizationKey;
        }
        else if (options.customHeaders) {
            headers = __assign(__assign({}, headers), options.customHeaders);
        }
        return headers;
    };
    return HttpService;
}());


;// CONCATENATED MODULE: ./src/integrations/cludo-analytics.ts
var cludo_analytics_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var cludo_analytics_generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};

/** The Cludo class is responsible for sending click/query/related searches logs to our analytics database */
var CludoAnalytics = /** @class */ (function () {
    function CludoAnalytics(enableTracking, cid, eid, searchApiUrl, intranet, siteKey) {
        this.enableTrackingRef = enableTracking;
        this.customerId = cid;
        this.engineId = eid;
        this.searchApiUrlPublic = searchApiUrl;
        this.isIntranet = intranet;
        this.authorizationKey = HttpService.getAuthorizationKey(cid, eid, siteKey);
    }
    CludoAnalytics.prototype.canProcess = function () {
        return this.enableTrackingRef.value;
    };
    CludoAnalytics.prototype.processQueryEvent = function (data) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            _this.pushStat('querylog', data).then(function () { resolve(); }, function () {
                console.error('Error processing click log');
                reject();
            });
        });
    };
    CludoAnalytics.prototype.processClickEvent = function (data) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            _this.pushStat('clicklog', data).then(function () { resolve(); }, function () {
                console.error('Error processing click log');
                reject();
            });
        });
    };
    CludoAnalytics.prototype.processRelatedSearchEvent = function (data) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            _this.pushStat('relatedsearcheslog', data).then(function () { resolve(); }, function () {
                console.error('Error processing click log');
                reject();
            });
        });
    };
    CludoAnalytics.prototype.processChatClickEvent = function (data) {
        return cludo_analytics_awaiter(this, void 0, void 0, function () {
            var baseUrl, requestUrl, _a;
            return cludo_analytics_generator(this, function (_b) {
                switch (_b.label) {
                    case 0:
                        baseUrl = HttpService.getBaseUrlForCustomer(this.customerId);
                        requestUrl = baseUrl + "/".concat(this.customerId, "/").concat(this.engineId, "/search/answer/click");
                        _b.label = 1;
                    case 1:
                        _b.trys.push([1, 3, , 4]);
                        // We don't use the response, but we need to await the request to ensure it is sent
                        return [4 /*yield*/, HttpService.postWithFetch(requestUrl, data, {
                                isIntranet: false,
                                authorizationKey: HttpService.getAuthorizationKey(this.customerId, this.engineId, 'SearchKey'),
                                contentType: 'application/json'
                            })];
                    case 2:
                        // We don't use the response, but we need to await the request to ensure it is sent
                        _b.sent();
                        return [2 /*return*/];
                    case 3:
                        _a = _b.sent();
                        console.error('Error processing chat click log');
                        return [3 /*break*/, 4];
                    case 4: return [2 /*return*/];
                }
            });
        });
    };
    CludoAnalytics.prototype.pushStat = function (type, statParams) {
        var pushstatUrl = this.searchApiUrlPublic + "/" + this.customerId + "/" + this.engineId + "/search/pushstat/" + type;
        var statQueryUrl = HttpService.buildUrl(pushstatUrl, statParams);
        var requestOptions = {
            isIntranet: this.isIntranet,
            authorizationKey: this.authorizationKey,
            contentType: 'application/json'
        };
        return HttpService.post(statQueryUrl, undefined, requestOptions);
    };
    return CludoAnalytics;
}());


;// CONCATENATED MODULE: ./src/integrations/google-analytics-4.ts
var google_analytics_4_assign = (undefined && undefined.__assign) || function () {
    google_analytics_4_assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return google_analytics_4_assign.apply(this, arguments);
};
var GoogleAnalytics4 = /** @class */ (function () {
    function GoogleAnalytics4(settings, trackingId) {
        this.websiteSettings = settings;
        this.googleAnalyticsTrackingId = trackingId;
    }
    GoogleAnalytics4.prototype.canProcess = function () {
        var _this = this;
        var GA4_CONFIG_PREFIX = 'G-';
        if (this.websiteSettings.enableGoogleAnalyticsIntegration && window.dataLayer !== undefined) {
            if (window.gtag !== undefined) {
                // If tracking ID is passed, check to see if it's for a GA4 data stream
                if (this.googleAnalyticsTrackingId && this.googleAnalyticsTrackingId.includes(GA4_CONFIG_PREFIX)) {
                    return true;
                }
                else {
                    // Check to see if any GA4 data streams are configured on the page
                    var configEvents = window.dataLayer.filter(function (x) { return x[0] === 'config'; });
                    var foundMatchedConfig_1 = false;
                    configEvents.forEach(function (event) {
                        var configId = event[1];
                        if (configId.includes(GA4_CONFIG_PREFIX)) {
                            _this.googleAnalyticsTrackingId = configId;
                            foundMatchedConfig_1 = true;
                        }
                    });
                    return foundMatchedConfig_1;
                }
            }
            else if (window.google_tag_manager !== undefined) {
                // Check for GA4 setup through GTM
                var match = Object.keys(window.google_tag_manager).find(function (key) { return key.includes(GA4_CONFIG_PREFIX); });
                return (match !== undefined);
            }
        }
        return false;
    };
    GoogleAnalytics4.prototype.processQueryEvent = function (analyticsData) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            var gtag = window.gtag;
            var resultCount = analyticsData.rc ? analyticsData.rc : 0;
            var searchResultParams = google_analytics_4_assign({ 'search_term': analyticsData.sw, 'q_cludoPage': analyticsData.pn, 'q_cludoResultCount': resultCount }, _this.buildFacetParameters(analyticsData) // custom cludo params
            );
            if (gtag) {
                gtag('event', 'view_search_results', searchResultParams);
            }
            else {
                window.dataLayer.push({ event: "view_search_results", eventModel: searchResultParams });
            }
            resolve();
        });
    };
    GoogleAnalytics4.prototype.processClickEvent = function (data) {
        return Promise.resolve();
    };
    /** Builds out custom cludo params in the form:
     *
     * `q_cludo<FacetName>: <facetValue>,<facetValue>,...` */
    GoogleAnalytics4.prototype.buildFacetParameters = function (analyticsData) {
        var facetParams = {};
        for (var selectedFacet in analyticsData.sf) {
            if (analyticsData.sf[selectedFacet] && analyticsData.sf[selectedFacet].length) {
                facetParams['q_cludo' + selectedFacet] = analyticsData.sf[selectedFacet].join(',');
            }
        }
        return facetParams;
    };
    return GoogleAnalytics4;
}());


;// CONCATENATED MODULE: ./src/integrations/google-legacy-analytics.ts

var GoogleLegacyAnalytics = /** @class */ (function () {
    function GoogleLegacyAnalytics(settings, trackingId) {
        this.websiteSettings = settings;
        this.googleAnalyticsTrackingId = trackingId;
    }
    GoogleLegacyAnalytics.prototype.canProcess = function () {
        return (this.websiteSettings.enableGoogleAnalyticsIntegration &&
            window.gtag === undefined &&
            (window.ga !== undefined || window._gaq !== undefined));
    };
    GoogleLegacyAnalytics.prototype.processQueryEvent = function (analyticsData) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            var path = LocationService.getPathname() + LocationService.getHash().substring(1);
            var ga = window.ga;
            var _gaq = window._gaq;
            var hasResultsMessage = 'Search with results';
            if (!analyticsData.rc || analyticsData.rc === 0) {
                hasResultsMessage = 'Search without results';
            }
            if (_this.isLegacyAnalyticsJsIntegration()) {
                var resolvedTrackingProperty = null;
                var allFoundTrackingProperties = ga.getAll();
                if (_this.googleAnalyticsTrackingId !== null) {
                    for (var i = 0; i < allFoundTrackingProperties.length; i++) {
                        if (allFoundTrackingProperties[i].get('trackingId') === _this.googleAnalyticsTrackingId) {
                            resolvedTrackingProperty = allFoundTrackingProperties[i];
                            break;
                        }
                    }
                    // Give a warning if no property found for given tracking ID
                    if (resolvedTrackingProperty === null) {
                        console.warn('CludoJs Warning: No Google Analytics tracking tag found for specified tracking ID');
                        resolvedTrackingProperty = allFoundTrackingProperties[0];
                    }
                }
                else {
                    resolvedTrackingProperty = allFoundTrackingProperties[0];
                }
                // Send PageView to be able using 'Site search' filter
                // Do not add any 'Event'/'Label' properties to this request
                ga(resolvedTrackingProperty.get('name') + '.send', {
                    'hitType': 'pageview',
                    'page': path,
                });
                // Send Event to be able track search events different
                // When we will divide search events we should set appropriated 'eventActions'
                ga(resolvedTrackingProperty.get('name') + '.send', 'event', {
                    'eventCategory': 'Cludo Search',
                    'eventAction': 'Search',
                    'eventLabel': hasResultsMessage,
                });
                resolve();
            }
            else if (Array.isArray(_gaq)) {
                _gaq.push(['_trackPageview', path]);
                _gaq.push('Cludo Search', 'Search', hasResultsMessage);
                resolve();
            }
            else {
                reject();
            }
        });
    };
    GoogleLegacyAnalytics.prototype.processClickEvent = function (data) {
        return Promise.resolve();
    };
    GoogleLegacyAnalytics.prototype.isLegacyAnalyticsJsIntegration = function () {
        var ga = window.ga;
        return (ga && ga.getAll && ga.getAll()[0] && ga.getAll()[0].get('clientId'));
    };
    return GoogleLegacyAnalytics;
}());


;// CONCATENATED MODULE: ./src/integrations/google-tag-manager.ts
var google_tag_manager_assign = (undefined && undefined.__assign) || function () {
    google_tag_manager_assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return google_tag_manager_assign.apply(this, arguments);
};
var GoogleTagManager = /** @class */ (function () {
    function GoogleTagManager(settings, gtmDataLayerName, deferEvent) {
        this.websiteSettings = settings;
        this.gtmDataLayerName = gtmDataLayerName;
        this.deferEvent = deferEvent;
    }
    Object.defineProperty(GoogleTagManager.prototype, "dataLayer", {
        get: function () {
            return window[this.gtmDataLayerName];
        },
        enumerable: false,
        configurable: true
    });
    GoogleTagManager.prototype.canProcess = function () {
        return (this.websiteSettings.enableGoogleTagManagerIntegration && Array.isArray(this.dataLayer));
    };
    GoogleTagManager.prototype.processQueryEvent = function (analyticsData) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            // Build event
            var cludoSearchEvent = {
                event: 'cludo_search_event',
                cludoEventData: google_tag_manager_assign({ resultCount: analyticsData.rc, responseTime: analyticsData.rt, eventType: analyticsData.ety, eventTrigger: analyticsData.etr, bannerIds: analyticsData.bnrs }, _this.getGTMBaseEventDataFromBaseLog(analyticsData))
            };
            _this.waitForDatalayerEvent(_this.deferEvent).then(function () {
                // Clear out object references in dataLayer
                Array.isArray(_this.dataLayer) && _this.dataLayer.push({
                    'cludoEventData.selectedFacets': undefined,
                    'cludoEventData.userTraits': undefined
                });
                // Push to dataLayer
                _this.dataLayer.push(cludoSearchEvent);
                resolve();
            }).catch(function () {
                console.warn('CludoJS Error: Wait for GTM event timed out');
                resolve();
            });
        });
    };
    GoogleTagManager.prototype.processClickEvent = function (analyticsData) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            // Build event
            var cludoClickEvent = {
                event: 'cludo_click_event',
                cludoEventData: google_tag_manager_assign({ clickType: analyticsData.cloi ? 'banner' : 'result', clickedUrl: analyticsData.clurl, clickedIndex: analyticsData.cli, clickedBannerId: analyticsData.cloi }, _this.getGTMBaseEventDataFromBaseLog(analyticsData))
            };
            _this.waitForDatalayerEvent(_this.deferEvent).then(function () {
                // Push to dataLayer
                _this.dataLayer.push(cludoClickEvent);
                resolve();
            }).catch(function () {
                console.warn('CludoJS Error: Wait for GTM event timed out');
                resolve();
            });
        });
    };
    GoogleTagManager.prototype.getGTMBaseEventDataFromBaseLog = function (data) {
        return {
            engineId: data.enid,
            query: data.sw,
            browserLanguage: data.brl,
            deviceType: data.dt,
            inputType: this.getInputType(data),
            selectedFacets: this.getFacetsArrayFromMap(data.sf),
            userTraits: this.getTraitsArray(data),
            pageNumber: parseInt(data.pn),
            userAgent: data.ua,
            timeStamp: data.a
        };
    };
    /** Convert from our base log input type to the format that GTM expects */
    GoogleTagManager.prototype.getInputType = function (data) {
        return (data.it === 'standard') ? 'typed' : 'voice';
    };
    /** Convert from our FacetMap to the format that GTM expects */
    GoogleTagManager.prototype.getFacetsArrayFromMap = function (selectedFacets) {
        var facetArr = [];
        Object.keys(selectedFacets).forEach(function (facetName) {
            facetArr.push({
                name: facetName,
                value: selectedFacets[facetName]
            });
        });
        return facetArr;
    };
    GoogleTagManager.prototype.getTraitsArray = function (data) {
        return data.trts ? data.trts.split(',') : [];
    };
    /** Allow clients to input event names that we should wait for before firing our own events */
    GoogleTagManager.prototype.waitForDatalayerEvent = function (eventName) {
        var _this = this;
        return new Promise(function (resolve, reject) {
            // If no event name is provided, resolve immediately (non-blocking)
            if (!eventName) {
                resolve();
                return;
            }
            // Resolve immediately if the event has already fired
            if (_this.dataLayerContainsEvent(eventName)) {
                resolve();
                return;
            }
            // Poll periodically until the event appears in the dataLayer or timeout
            var polls = 0;
            var interval = setInterval(function () {
                if (_this.dataLayerContainsEvent(eventName)) {
                    clearInterval(interval);
                    resolve();
                }
                else {
                    if (polls > 100) {
                        reject();
                    }
                    polls++;
                }
            }, 100);
        });
    };
    GoogleTagManager.prototype.dataLayerContainsEvent = function (eventName) {
        return Array.isArray(this.dataLayer) && this.dataLayer.some(function (item) { return (item === null || item === void 0 ? void 0 : item.event) === eventName; });
    };
    return GoogleTagManager;
}());


;// CONCATENATED MODULE: ./src/integrations/google-universal-analytics.ts

var GoogleUniversalAnalytics = /** @class */ (function () {
    function GoogleUniversalAnalytics(settings, trackingId) {
        this.websiteSettings = settings;
        this.googleAnalyticsTrackingId = trackingId;
    }
    GoogleUniversalAnalytics.prototype.canProcess = function () {
        var _this = this;
        var UA_CONFIG_PREFIX = 'UA-';
        if (this.websiteSettings.enableGoogleAnalyticsIntegration && window.gtag !== undefined && window.dataLayer !== undefined) {
            // If tracking ID is passed, check to see if it's for a UA data stream
            if (this.googleAnalyticsTrackingId && this.googleAnalyticsTrackingId.includes(UA_CONFIG_PREFIX)) {
                return true;
            }
            else {
                // Check to see if any UA data streams are configured on the page
                var configEvents = window.dataLayer.filter(function (x) { return x[0] === 'config'; });
                var foundMatchedConfig_1 = false;
                configEvents.forEach(function (event) {
                    var configId = event[1];
                    if (configId.includes(UA_CONFIG_PREFIX)) {
                        _this.googleAnalyticsTrackingId = configId;
                        foundMatchedConfig_1 = true;
                    }
                });
                return foundMatchedConfig_1;
            }
        }
        return false;
    };
    GoogleUniversalAnalytics.prototype.processQueryEvent = function (analyticsData) {
        return new Promise(function (resolve, reject) {
            var path = LocationService.getPathname() + LocationService.getHash().substring(1);
            var gtag = window.gtag;
            var hasResultsMessage = 'Search with results';
            if (!analyticsData.rc || analyticsData.rc === 0) {
                hasResultsMessage = 'Search without results';
            }
            // Send virtual page view to track search
            gtag('set', { 'page_path': path });
            gtag('event', 'page_view');
            // Send custom results message
            gtag('event', 'Search', {
                'event_category': 'Cludo Search',
                'event_label': hasResultsMessage,
            });
            resolve();
        });
    };
    GoogleUniversalAnalytics.prototype.processClickEvent = function (data) {
        return Promise.resolve();
    };
    return GoogleUniversalAnalytics;
}());


;// CONCATENATED MODULE: ./src/integrations/site-improve-analytics.ts

var SiteImproveAnalytics = /** @class */ (function () {
    function SiteImproveAnalytics(settings) {
        this.websiteSettings = settings;
    }
    SiteImproveAnalytics.prototype.canProcess = function () {
        return (this.websiteSettings.enableSiteimproveAnalyticsIntegration === true && window._sz !== undefined);
    };
    SiteImproveAnalytics.prototype.processQueryEvent = function (analyticsData) {
        return new Promise(function (resolve, reject) {
            try {
                var _sz = window['_sz'];
                if (typeof _sz !== 'undefined') {
                    var href = LocationService.getHref();
                    var newHref = href.replace(/\/?#\/?/, '/hash/'); //Replacing # in URL due to Siteimproves default behaviour to strip hashtag from URL
                    var szData = [];
                    // The URL that will be displayed in analytics tool
                    szData.push(['ourl', newHref]);
                    // The title of the page to be displayed in analytics tool
                    szData.push(['title', window.document.title]);
                    // Update the searchword and hits values
                    szData.push(['sw', analyticsData.sw]);
                    szData.push(['hits', analyticsData.rc]);
                    //_sz.push(['trackdynamic', [['url', 'https://www.example.com/'], ['sw', 'haj'], ['hits', 666]]]);
                    _sz.push(['trackdynamic', szData]);
                    resolve();
                }
                else {
                    reject('Error: SiteImprove integration is not available on this page');
                }
            }
            catch (e) {
                reject(e);
            }
        });
    };
    SiteImproveAnalytics.prototype.processClickEvent = function (data) {
        return Promise.resolve();
    };
    return SiteImproveAnalytics;
}());


;// CONCATENATED MODULE: ./src/integrations/integrations.ts






var AnalyticsIntegrationFactory = /** @class */ (function () {
    function AnalyticsIntegrationFactory() {
    }
    AnalyticsIntegrationFactory.getIntegrationsCommunicator = function (context) {
        return new AnalyticsIntegrationCommunicator(context);
    };
    AnalyticsIntegrationFactory.getIntegrations = function (context) {
        if (context.helpers.isEmpty(context.websiteSettings)) {
            console.warn("Attempted to initialize analytics integrations before customer settings were available");
            return [];
        }
        else {
            return [
                new SiteImproveAnalytics(context.websiteSettings),
                new GoogleUniversalAnalytics(context.websiteSettings, context.googleAnalyticsTrackingId),
                new GoogleLegacyAnalytics(context.websiteSettings, context.googleAnalyticsTrackingId),
                new GoogleAnalytics4(context.websiteSettings, context.googleAnalyticsTrackingId),
                new GoogleTagManager(context.websiteSettings, context.gtmDataLayerName, context.waitForGtmEvent),
                new CludoAnalytics(context.enableExtendedTrackingRef, context.customerId, context.engineId, context.searchApiUrlPublic, context.intranetSearch, context.searchSiteKey)
            ];
        }
    };
    return AnalyticsIntegrationFactory;
}());

var AnalyticsIntegrationCommunicator = /** @class */ (function () {
    function AnalyticsIntegrationCommunicator(context) {
        this.integrations = AnalyticsIntegrationFactory.getIntegrations(context);
    }
    AnalyticsIntegrationCommunicator.prototype.processClickEvents = function (data) {
        if (!this.isValidLogObject(data)) {
            return [];
        }
        return this.integrations.filter(function (integration) { return integration.canProcess(); })
            .map(function (integration) { return integration.processClickEvent(data); });
    };
    AnalyticsIntegrationCommunicator.prototype.processQueryEvents = function (data) {
        if (!this.isValidLogObject(data)) {
            return [];
        }
        return this.integrations.filter(function (integration) { return integration.canProcess(); })
            .map(function (integration) { return integration.processQueryEvent(data); });
    };
    AnalyticsIntegrationCommunicator.prototype.processRelatedSearchEvents = function (data) {
        if (!this.isValidLogObject(data)) {
            return [];
        }
        return this.integrations.filter(function (integration) { return integration.canProcess(); })
            .map(function (integration) {
            if (integration.processRelatedSearchEvent) {
                return integration.processRelatedSearchEvent(data);
            }
        });
    };
    AnalyticsIntegrationCommunicator.prototype.processChatClickEvents = function (data) {
        return this.integrations.filter(function (integration) { return integration.canProcess(); })
            .map(function (integration) {
            if (integration.processChatClickEvent) {
                return integration.processChatClickEvent(data);
            }
        });
    };
    AnalyticsIntegrationCommunicator.prototype.isValidLogObject = function (data) {
        return data.sw !== undefined && data.sw !== '';
    };
    return AnalyticsIntegrationCommunicator;
}());


;// CONCATENATED MODULE: ./src/conversation-service.ts
var conversation_service_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var conversation_service_generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};


/** Service that can set and retrieve conversations from storage based on current tracking restrictions */
var ConversationService = /** @class */ (function () {
    function ConversationService(storageService) {
        this.storageService = storageService;
    }
    /** Store conversations */
    ConversationService.prototype.storeConversations = function (conversations) {
        this.storageService.setItem(StorageKey.Conversations, conversations);
    };
    /** Get conversations from storage */
    ConversationService.prototype.getConversationsFromStorage = function () {
        return this.storageService.getItem(StorageKey.Conversations) || [];
    };
    /** Send a question to our QA service */
    ConversationService.prototype.sendQuestion = function (customerId, engineId, requestBody, controller) {
        return conversation_service_awaiter(this, void 0, void 0, function () {
            var baseUrl, requestUrl, response, e_1;
            return conversation_service_generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!customerId)
                            return [2 /*return*/];
                        baseUrl = HttpService.getBaseUrlForCustomer(customerId, 4);
                        requestUrl = baseUrl + "/".concat(customerId, "/").concat(engineId, "/search/answer");
                        _a.label = 1;
                    case 1:
                        _a.trys.push([1, 3, , 4]);
                        return [4 /*yield*/, HttpService.postWithFetch(requestUrl, requestBody, {
                                isIntranet: false,
                                authorizationKey: HttpService.getAuthorizationKey(customerId, engineId, 'SearchKey'),
                                contentType: 'application/json',
                                abortSignal: controller.signal
                            })];
                    case 2:
                        response = _a.sent();
                        return [2 /*return*/, JSON.parse(response)];
                    case 3:
                        e_1 = _a.sent();
                        console.error('Error sending question', e_1);
                        return [3 /*break*/, 4];
                    case 4: return [2 /*return*/];
                }
            });
        });
    };
    /** Send feedback data regarding an exchange */
    ConversationService.prototype.sendFeedbackData = function (customerId, engineId, feedbackData) {
        return conversation_service_awaiter(this, void 0, void 0, function () {
            var baseUrl, requestUrl, e_2;
            return conversation_service_generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!customerId)
                            return [2 /*return*/];
                        baseUrl = HttpService.getBaseUrlForCustomer(customerId);
                        requestUrl = baseUrl + "/".concat(customerId, "/").concat(engineId, "/search/answer/feedback");
                        _a.label = 1;
                    case 1:
                        _a.trys.push([1, 3, , 4]);
                        return [4 /*yield*/, HttpService.postWithFetch(requestUrl, feedbackData, {
                                isIntranet: false,
                                authorizationKey: HttpService.getAuthorizationKey(customerId, engineId, 'SearchKey'),
                                contentType: 'application/json'
                            })];
                    case 2:
                        _a.sent();
                        return [3 /*break*/, 4];
                    case 3:
                        e_2 = _a.sent();
                        console.error('Error sending feedback data', e_2);
                        return [3 /*break*/, 4];
                    case 4: return [2 /*return*/];
                }
            });
        });
    };
    return ConversationService;
}());


;// CONCATENATED MODULE: ./src/settings-service.ts
var settings_service_assign = (undefined && undefined.__assign) || function () {
    settings_service_assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return settings_service_assign.apply(this, arguments);
};

/** Class for encapsulating logic around retrieval of settings via web service */
var SettingsService = /** @class */ (function () {
    function SettingsService() {
    }
    SettingsService.getPublicSettingsByEngine = function (customerId, engineId, apiUrl, authKey, searchSiteKey, isIntranet, customHeaders) {
        if (searchSiteKey === void 0) { searchSiteKey = 'SearchKey'; }
        if (isIntranet === void 0) { isIntranet = false; }
        if (customHeaders === void 0) { customHeaders = {}; }
        var defaultUrl = HttpService.getBaseUrlForCustomer(customerId);
        var url = apiUrl ? apiUrl : defaultUrl;
        var authorizationKey = (!isIntranet && !authKey) ? HttpService.getAuthorizationKey(customerId, engineId, searchSiteKey) : authKey;
        var requestOptions = {
            isIntranet: isIntranet,
            authorizationKey: authorizationKey,
            contentType: 'application/json'
        };
        if (isIntranet) {
            requestOptions = settings_service_assign(settings_service_assign({}, requestOptions), { customHeaders: customHeaders });
        }
        return HttpService.get(url + "/" + customerId + "/" + engineId + "/websites/publicsettings", requestOptions);
    };
    // See endpoint documentation here: https://cludosearch.atlassian.net/browse/EB-61
    SettingsService.getPublicSettingsByExperience = function (customerId, engineId, experienceId, apiUrl, authKey, searchSiteKey, isIntranet, customHeaders) {
        if (searchSiteKey === void 0) { searchSiteKey = 'SearchKey'; }
        if (isIntranet === void 0) { isIntranet = false; }
        if (customHeaders === void 0) { customHeaders = {}; }
        var defaultUrl = HttpService.getBaseUrlForCustomer(customerId, 4);
        var url = apiUrl ? apiUrl : defaultUrl;
        var authorizationKey = (!isIntranet && !authKey) ? HttpService.getAuthorizationKey(customerId, engineId, searchSiteKey) : authKey;
        var requestOptions = {
            isIntranet: isIntranet,
            authorizationKey: authorizationKey,
            contentType: 'application/json'
        };
        if (isIntranet) {
            requestOptions = settings_service_assign(settings_service_assign({}, requestOptions), { customHeaders: customHeaders });
        }
        return HttpService.getWithFetch(url + "/" + customerId + "/experiences/" + experienceId + "/settings", requestOptions);
    };
    return SettingsService;
}());


;// CONCATENATED MODULE: ./src/client-templates/client-template-functions.ts
/** This function is called externally through the instantiation process */
function setClientTemplateComponentsController(controller) {
    this.clientTemplatesComponentController = controller;
}

;// CONCATENATED MODULE: ./src/client-templates/client-template-autocomplete-functions.ts
/** Populates autocomplete response data and emits the autocomplete event */
function autocompleteTemplateClient(data, searchInputElement, suppressCallback) {
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    if (this.richAutocomplete) {
        this.richAutocompleteTemplateClient(data, searchInputElement, suppressCallback);
    }
    else {
        this.standardAutocompleteTemplateClient(data, searchInputElement, suppressCallback);
    }
}
/**
 * Renders rich autocomplete using client-side templates
 * @param {object} data Autocomplete JSON response
 * @param {Element} searchInputElement
 * @param {boolean} suppressCallback
 * @returns
 */
function richAutocompleteTemplateClient(data, searchInputElement, suppressCallback) {
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    // Return if this isn't the most recent autocomplete call, or if autocomplete is hidden
    if ((data.query && this.params.query !== data.query) || this.hideAutocomplete) {
        return;
    }
    searchInputElement && this.prepareAutocompleteContainer(searchInputElement);
    // Update stored data
    this.selectedIndex = -1;
    this.autocompleteResponseData = data;
    this.storedRecentSearchesClient = []; // hide recent searches when we have a query
    // Process autocomplete event
    this.clientTemplatesComponentController.processEvent('afterautocomplete');
    if (this.customCallbackAfterAutocomplete && !suppressCallback) {
        this.customCallbackAfterAutocomplete();
    }
}
/**
 * Renders standard autocomplete using client-side templates
 * @param {string[]} data Collection of autocomplete suggestions
 * @param {Element} searchInputElement
 * @param {boolean} suppressCallback
 * @returns
 */
function standardAutocompleteTemplateClient(data, searchInputElement, suppressCallback) {
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    if (this.hideAutocomplete) {
        return;
    }
    searchInputElement && this.prepareAutocompleteContainer(searchInputElement);
    this.selectedIndex = -1;
    this.storedRecentSearchesClient = [];
    // Process autocomplete event
    this.clientTemplatesComponentController.processEvent('afterautocomplete');
    if (this.customCallbackAfterAutocomplete && !suppressCallback) {
        this.customCallbackAfterAutocomplete();
    }
}
/** Clears the `autocompleteResponseData` property to an empty object of the correct shape  */
function clearStoredAutocompleteResponseData() {
    this.autocompleteResponseData = {
        Facets: null,
        QueryId: null,
        ResponseTime: null,
        SearchResult: '',
        TotalResults: null,
        TotalSuggestions: null,
        query: '',
        Suggestions: [],
        Results: [],
    };
    this.storedRecentSearchesClient = [];
}
/** Resets the stored autocomplete response data, the selected index, and hides autocomplete
 *
 * Also removes the autocomplete hint element, and removes the aria attributes from the search input that link to
 * the autocomplete hint and autocomplete container
 */
function autocompleteRestoreClient(clearRequestTimer) {
    var _this = this;
    if (clearRequestTimer === void 0) { clearRequestTimer = true; }
    // if the "debug" flag is set to true, then forgo removing the autocomplete container and results
    if (this.debug) {
        return;
    }
    if (this.autocompleteDebounceTimerId && clearRequestTimer) {
        clearTimeout(this.autocompleteDebounceTimerId);
        this.autocompleteDebounceTimerId = null;
    }
    this.selectedIndex = -1;
    this.hideAutocomplete = true;
    if (!this.headlessSearch) {
        this.helpers.removeAttributesWithSelector("aria-controls", "search_autocomplete");
        this.helpers.removeAttributesWithSelector("aria-describedby", "autocomplete_hint");
        this.searchComponentsKeys.forEach(function (key) {
            var _a;
            var componentGroup = _this.searchComponentsDictionary[key];
            var searchBoxComponent = componentGroup.searchBoxInput;
            var autocompleteComponent = (_a = componentGroup.wrapper) === null || _a === void 0 ? void 0 : _a.querySelector('#search_autocomplete');
            searchBoxComponent && searchBoxComponent.setAttribute("aria-expanded", "false");
            searchBoxComponent && searchBoxComponent.removeAttribute("aria-activedescendant");
            autocompleteComponent && (autocompleteComponent.style.display = 'none');
        });
    }
    this.clearStoredAutocompleteResponseData();
    this.clientTemplatesComponentController.processEvent('afterautocomplete');
}
/** Creates or unhides autocomplete container for specific search input */
function prepareAutocompleteContainer(searchInputElement) {
    var autocompleteContainer = searchInputElement.parentElement.querySelector('#search_autocomplete');
    // Create container if none exist
    if (!autocompleteContainer) {
        autocompleteContainer = this.helpers.addElement(searchInputElement.parentElement, 'search_autocomplete', 'search_autocomplete');
        // ensure that it is focusable so that we can detect and process blur events in the right order
        autocompleteContainer.tabIndex = 0;
        /* Create autocomplete hint element and append to search input */
        this.addAutocompleteHintToSearchInput(searchInputElement);
    }
    searchInputElement && searchInputElement.setAttribute("aria-expanded", "true");
    if (autocompleteContainer.style.display === 'none') {
        autocompleteContainer.style.display = null;
    }
}
/** Emits keyboard navigation events for updating/selecting autocomplete items */
function autocompleteKeyboardSelectionChange(keyNum) {
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    if (keyNum === this.helpers.DOWN) {
        this.clientTemplatesComponentController.processEvent('autocompleteSelectionNext');
    }
    if (keyNum === this.helpers.UP) {
        this.clientTemplatesComponentController.processEvent('autocompleteSelectionPrev');
    }
    if (keyNum === this.helpers.ENTER) {
        this.clientTemplatesComponentController.processEvent('autocompleteSetSelection');
    }
}
function autocompleteSetSelectedSuggestion(suggestion, suggestionIndex) {
    var _this = this;
    this.params.query = this.helpers.stripSpecialChars(suggestion);
    if (this._handleQuickLinks()) {
        return;
    }
    // TODO: Assess what needs to change to support overlay search
    // if (this.isOverlaySearch) {
    //     this.overlayOpenModalWithSearch();
    // }
    if (this.resetFiltersBeforeSearch) {
        this.params.filters = {};
    }
    // Set pending ac values. For index, we add one to make it 1-based. 
    this.pendingAcTitle = this.lastAcQuery;
    this.pendingAcIndex = suggestionIndex + 1;
    this.searchComponentsKeys.forEach(function (key) {
        var componentGroup = _this.searchComponentsDictionary[key];
        // Check if this is the component group that is showing autocomplete
        if (componentGroup.wrapper.querySelector('#search_autocomplete') !== null) {
            // Set any preset facets on the active component group
            _this.setFacetsBeforeSearch(componentGroup.searchBoxFacets);
        }
    });
    this.setInputTypeAndSearch(this.inputTypeStandardKey);
}
function autocompleteSetSelectedResult(selectedItem) {
    var _this = this;
    var selectedItemText = selectedItem.Fields['Title'].Value;
    var selectedUrl = selectedItem.Fields['Url'].Value;
    // Build clickstat for result
    this.clickStat = {
        index: selectedItem.ResultIndex,
        url: selectedUrl,
        title: selectedItemText,
        page: '1'
    };
    this.pushClickLog(this._buildClickLogObjectForRichAutocompleteLink(), function () {
        _this.redirectToUrl(selectedUrl);
    });
}
function autocompleteSetSelectedRecentSearch(recentSearch, recentSearchIndex) {
    this.autocompleteSetSelectedSuggestion(recentSearch, recentSearchIndex);
}
/** Populate autocomplete with the data from Instant Suggestions */
function setInstantSuggestionsClient(suggestions, recentSearches) {
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    this.hideAutocomplete = false;
    this.autocompleteResponseData.InstantSuggestions = suggestions ? this.getAutocompleteSuggestionsFromInstantSuggestions(suggestions) : [];
    this.storedRecentSearchesClient = recentSearches ? recentSearches.items : [];
    this.clientTemplatesComponentController.processEvent('afterautocomplete');
}
/** Helper function for transforming an InstantSuggesetionSection into a TypedDocument array */
function getAutocompleteSuggestionsFromInstantSuggestions(suggestions) {
    return suggestions.items.map(function (suggestion) {
        return {
            ResultIndex: 0,
            Sortings: null,
            Score: 0,
            FieldNames: ["Title"],
            Fields: {
                Title: {
                    Field: "Title",
                    Highlights: [],
                    IsArray: false,
                    Value: suggestion,
                    Values: [suggestion]
                }
            }
        };
    });
}
/** Helper function to set the id passed by the React template to the aria-activedescendant attribute **/
function setActiveDescendantToSuggestions(id) {
    var _this = this;
    this.searchComponentsKeys.forEach(function (key) {
        var componentGroup = _this.searchComponentsDictionary[key];
        var searchBoxComponent = componentGroup.searchBoxInput;
        if (searchBoxComponent && (searchBoxComponent.parentElement.querySelector('#search_autocomplete') !== null)) {
            searchBoxComponent && searchBoxComponent.setAttribute("aria-activedescendant", id);
        }
    });
}

;// CONCATENATED MODULE: ./src/types/response-types.ts
var ClientSearchResponseObject = /** @class */ (function () {
    function ClientSearchResponseObject(response) {
        var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m;
        // Initialize response object with optional existing response values
        // Otherwise, default to empty object
        this.Facets = (_a = response === null || response === void 0 ? void 0 : response.Facets) !== null && _a !== void 0 ? _a : {};
        this.TypedDocuments = (_b = response === null || response === void 0 ? void 0 : response.TypedDocuments) !== null && _b !== void 0 ? _b : [];
        this.TotalDocument = (_c = response === null || response === void 0 ? void 0 : response.TotalDocument) !== null && _c !== void 0 ? _c : 0;
        this.FixedQuery = (_d = response === null || response === void 0 ? void 0 : response.FixedQuery) !== null && _d !== void 0 ? _d : '';
        this.Banners = (_e = response === null || response === void 0 ? void 0 : response.Banners) !== null && _e !== void 0 ? _e : [];
        this.ResponseTime = (_f = response === null || response === void 0 ? void 0 : response.ResponseTime) !== null && _f !== void 0 ? _f : 0;
        this.QueryId = (_g = response === null || response === void 0 ? void 0 : response.QueryId) !== null && _g !== void 0 ? _g : null;
        this.Suggestions = (_h = response === null || response === void 0 ? void 0 : response.Suggestions) !== null && _h !== void 0 ? _h : [];
        this.Synonyms = (_j = response === null || response === void 0 ? void 0 : response.Synonyms) !== null && _j !== void 0 ? _j : [];
        this.TopHits = (_k = response === null || response === void 0 ? void 0 : response.TopHits) !== null && _k !== void 0 ? _k : [];
        this.GenerativeAnswerAvailable = (_l = response === null || response === void 0 ? void 0 : response.GenerativeAnswerAvailable) !== null && _l !== void 0 ? _l : null;
        this.query = (_m = response === null || response === void 0 ? void 0 : response.query) !== null && _m !== void 0 ? _m : null;
    }
    return ClientSearchResponseObject;
}());


;// CONCATENATED MODULE: ./src/client-templates/client-template-search-functions.ts
var client_template_search_functions_assign = (undefined && undefined.__assign) || function () {
    client_template_search_functions_assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return client_template_search_functions_assign.apply(this, arguments);
};

/**
 * Do pre-search handling to support client templates
 *  - Ensure that the necessary container elements are attached
 *  - Reset the storedSearchResponseData object
 *  - Emit the 'beforeSearch' event to the search components library to update components as necessary
 */
function clientTemplateBeforeSearch() {
    if (this.params.page === 1 || !this.endlessScroll) {
        this.clearStoredSearchResponseData(this.params.query);
        if (!this.headlessSearch) {
            this.clientTemplatePrepareResultContainer();
        }
    }
    // Clear out error, if there was one
    this.storedError = {};
    // Emit 'beforesearch' event
    this.clientTemplatesComponentController.processEvent('beforesearch');
}
/**
 * Ensures that the result containers exist in the markup so that the components
 *  can be properly mounted
 */
function clientTemplatePrepareResultContainer() {
    var resultsContainer = this.elemSearchResults.results.querySelector('.search-results-container');
    if (!resultsContainer) {
        resultsContainer = document.createElement('div');
        resultsContainer.className = 'search-results-container';
        this.elemSearchResults.results.insertAdjacentElement('beforeend', resultsContainer);
    }
}
/**
 * Map the web service object to one appopriate for the client templates
 * @param data Search response object returned from the load results web service
 * @returns Mapped response state object
 */
function mapClientSearchResponse(data) {
    return {
        Banners: data.Banners,
        Facets: data.Facets,
        FixedQuery: data.FixedQuery,
        QueryId: data.QueryId,
        Query: data.query,
        ResponseTime: data.ResponseTime,
        ResultCount: data.TotalDocument,
        Suggestions: data.Suggestions.map(function (suggestion) { return suggestion.Text; }),
        Synonyms: [],
        TypedDocuments: data.TypedDocuments,
        TopHits: data.TopHits,
        GenerativeAnswerAvailable: data.GenerativeAnswerAvailable,
        RelatedSearchDocuments: data.RelatedSearchDocuments || [],
        ResultCountMessage: this.getResultCountHtml({
            fixedQuery: data.FixedQuery,
            totalDocuments: data.TotalDocument
        })
    };
}
/**
     * Renders search results and facets using client-side templates
     * @param {object} data Search results JSON response
     * @param {Element} placeholder Search results placeholder element
     */
function searchResultTemplateClient(data, placeholder) {
    var _this = this;
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    this.isLoadingResults = false;
    if (this.publicSettingsRetrieved === false) {
        // call itself in 250 ms to make sure we have public settings
        this.reCallSearchResultTemplateTimer = window.setTimeout(function () {
            _this.searchResultTemplateClient(data, placeholder);
        }, 250);
    }
    else {
        this.totalDocuments = data.TotalDocument; // :)
        this.fixedQuery = data.FixedQuery; // :)
        this.banners = data.Banners; // :)
        this.responseTime = data.ResponseTime; // :)
        this.queryId = data.QueryId; // :)
        this.track();
        // Render outside banners first, if enabled
        this.renderOutsideBanners(data, placeholder);
        if (this.endlessScroll) {
            this.onEndlessScrollResultsReturned(data);
        }
        else {
            this.storedSearchResponseData = this.mapClientSearchResponse(data);
        }
        // At this point, we have an up-to-date storedSearchResponseData
        // Here we emit the 'aftersearch' event
        // If the results have changed, this will trigger a re-render of the search results component
        this.clientTemplatesComponentController.processEvent('aftersearch', this.storedSearchResponseData);
        // TODO support related searches in client templates
        // NEED related searches object in response in order to do anything here
        // if (placeholder.relatedSearches && data && data.RelatedSearchesResult) {
        //     var translatedRelatedSearchesResult = this.translateProvider.translateTokens(data.RelatedSearchesResult);
        //     for (var i = 0; i < placeholder.relatedSearches.length; i++) {
        //         placeholder.relatedSearches[i].innerHTML = '';
        //         placeholder.relatedSearches[i].innerHTML += translatedRelatedSearchesResult;
        //     }
        // }
        // else if (placeholder.relatedSearches && data && !data.RelatedSearchesResult) {
        //     for (var i = 0; i < placeholder.relatedSearches.length; i++) {
        //         placeholder.relatedSearches[i].innerHTML = '';
        //     }
        // }
        this.isSearchAfterRedirect = false;
        // TODO support this?
        if (!this.pageInitFromBackForward) {
            this._handleQuickLinks();
        }
        // Perform custom callback after search
        if (this.customCallbackAfterSearch) {
            this.customCallbackAfterSearch(data);
        }
    }
}
/**
 * Handle client-side rendering of search results when endless scroll is enabled
 * @param {object} data Search Results JSON data
 */
function onEndlessScrollResultsReturned(data) {
    // Sanity check
    if (!this.clientTemplates) {
        console.log('CludoJs Error: Method is not supported');
        return;
    }
    this.isLazyLoading = false;
    // Update storedSearchResponseData property
    (this.params.page === 1)
        ? this.storedSearchResponseData = this.mapClientSearchResponse(data)
        : appendStoredSearchResponseData(this.storedSearchResponseData, data);
}
/**
 * Resets the storedSearchResponseData object to the empty state
 */
function clearStoredSearchResponseData(curQuery) {
    if (curQuery === void 0) { curQuery = null; }
    var queryIsChanged = !this.storedSearchResponseData ||
        curQuery !== this.storedSearchResponseData.Query;
    var persistedResponseValues = queryIsChanged ? {} : {
        Facets: this.storedSearchResponseData.Facets,
        ResultCount: this.storedSearchResponseData.ResultCount,
        ResultCountMessage: this.storedSearchResponseData.ResultCountMessage,
        FixedQuery: this.storedSearchResponseData.FixedQuery,
        Query: this.storedSearchResponseData.Query,
        Suggestions: this.storedSearchResponseData.Suggestions
    };
    var clearedResponse = new ClientSearchResponseObject();
    var clearedResponseState = client_template_search_functions_assign(client_template_search_functions_assign({}, this.mapClientSearchResponse(clearedResponse)), { ResultCountMessage: '' });
    this.storedSearchResponseData = client_template_search_functions_assign(client_template_search_functions_assign({}, clearedResponseState), persistedResponseValues);
}
/**
 * Appends a new batch of search results with the existing results in the storedSearchResponseData property
 * @param data One "batch" of results returned via the endless scroll incremental loading
 */
function appendStoredSearchResponseData(state, data) {
    state.TypedDocuments = state.TypedDocuments.concat(data.TypedDocuments);
}

;// CONCATENATED MODULE: ./src/client-templates/client-template-error-functions.ts
function errorTemplateClient(msg) {
    if (this.resultsWrapper != null || this.headlessSearch) {
        this.clearStoredSearchResponseData();
        this.storedError = { message: msg };
        this.isLoadingResults = false;
        this.clientTemplatesComponentController.processEvent('error');
    }
}

;// CONCATENATED MODULE: ./src/trending-pages-service.ts
var trending_pages_service_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var trending_pages_service_generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};

var TrendingPagesService = /** @class */ (function () {
    function TrendingPagesService() {
    }
    /** Get trending pages for customer and engine based on passed parameters */
    TrendingPagesService.prototype.getTrendingPages = function (customerId, engineId, trendingPagesOptions, requestOptions) {
        return trending_pages_service_awaiter(this, void 0, void 0, function () {
            return trending_pages_service_generator(this, function (_a) {
                return [2 /*return*/, this.getTrendingPagesByType(customerId, engineId, trendingPagesOptions, requestOptions, 'trending')];
            });
        });
    };
    /** Get popular pages for customer and engine based on passed parameters */
    TrendingPagesService.prototype.getPopularPages = function (customerId, engineId, popularPagesOptions, requestOptions) {
        return trending_pages_service_awaiter(this, void 0, void 0, function () {
            return trending_pages_service_generator(this, function (_a) {
                return [2 /*return*/, this.getTrendingPagesByType(customerId, engineId, popularPagesOptions, requestOptions, 'popular')];
            });
        });
    };
    TrendingPagesService.prototype.getTrendingPagesByType = function (customerId, engineId, trendingPagesOptions, requestOptions, type) {
        return trending_pages_service_awaiter(this, void 0, void 0, function () {
            var baseUrlForCustomer, baseRequestUrl, finalRequestUrl, responseJSON, _a;
            return trending_pages_service_generator(this, function (_b) {
                switch (_b.label) {
                    case 0:
                        baseUrlForCustomer = HttpService.getBaseUrlForCustomer(customerId, 4);
                        baseRequestUrl = "".concat(baseUrlForCustomer, "/").concat(customerId, "/").concat(engineId, "/content/recommendations/pages/").concat(type);
                        finalRequestUrl = HttpService.buildUrl(baseRequestUrl, trendingPagesOptions);
                        _b.label = 1;
                    case 1:
                        _b.trys.push([1, 3, , 4]);
                        return [4 /*yield*/, HttpService.getWithFetch(finalRequestUrl, requestOptions)];
                    case 2:
                        responseJSON = _b.sent();
                        return [2 /*return*/, JSON.parse(responseJSON)];
                    case 3:
                        _a = _b.sent();
                        console.error('Error fetching trending pages');
                        return [3 /*break*/, 4];
                    case 4: return [2 /*return*/];
                }
            });
        });
    };
    return TrendingPagesService;
}());


;// CONCATENATED MODULE: ./src/related-pages-service.ts
var related_pages_service_assign = (undefined && undefined.__assign) || function () {
    related_pages_service_assign = Object.assign || function(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return related_pages_service_assign.apply(this, arguments);
};
var related_pages_service_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var related_pages_service_generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};


var URL_SPLIT_REGEX = /\/|_/g;
var RelatedPagesService = /** @class */ (function () {
    function RelatedPagesService(cid, eid, searchApiUrl, intranet, siteKey) {
        this.customerId = cid;
        this.engineId = eid;
        this.searchApiUrlPublic = searchApiUrl;
        this.isIntranet = intranet;
        this.authorizationKey = HttpService.getAuthorizationKey(cid, eid, siteKey);
    }
    RelatedPagesService.prototype.getRelatedPages = function (url, overrideParams) {
        return related_pages_service_awaiter(this, void 0, void 0, function () {
            var parsedQuery, httpServiceUrl, requestHeaders, requestBody, response, parsedResponse, _a;
            return related_pages_service_generator(this, function (_b) {
                switch (_b.label) {
                    case 0:
                        parsedQuery = this.joinUrlIntoQuery(url);
                        if (!parsedQuery.length) {
                            return [2 /*return*/, new ClientSearchResponseObject()];
                        }
                        httpServiceUrl = this.searchApiUrlPublic + "/" + this.customerId + "/" + this.engineId + "/" + "search";
                        requestHeaders = {
                            isIntranet: this.isIntranet,
                            authorizationKey: this.authorizationKey,
                            contentType: 'application/json',
                        };
                        requestBody = related_pages_service_assign({ ResponseType: "Json", query: parsedQuery, perPage: 5, searchContext: "search404" }, overrideParams);
                        _b.label = 1;
                    case 1:
                        _b.trys.push([1, 4, , 5]);
                        return [4 /*yield*/, HttpService.postWithFetch(httpServiceUrl, requestBody, requestHeaders)];
                    case 2:
                        response = _b.sent();
                        return [4 /*yield*/, JSON.parse(response)];
                    case 3:
                        parsedResponse = _b.sent();
                        return [2 /*return*/, parsedResponse];
                    case 4:
                        _a = _b.sent();
                        console.error('CludoJS: Error fetching related pages');
                        return [2 /*return*/, new ClientSearchResponseObject()];
                    case 5: return [2 /*return*/];
                }
            });
        });
    };
    // To get a search query, we join all the relevant parts from the 
    // provided URL into a single query string
    RelatedPagesService.prototype.joinUrlIntoQuery = function (url) {
        var urlObject = new URL(url);
        var splitPath = this.splitPath(urlObject);
        var splitQueryParams = this.splitQueryParams(urlObject);
        var joinedQuery = splitPath.concat(splitQueryParams).join(' ');
        return joinedQuery;
    };
    // Parts from the main path after the schema/domain
    RelatedPagesService.prototype.splitPath = function (urlObject) {
        var splitPath = urlObject.pathname.split(URL_SPLIT_REGEX);
        var trimmedPath = splitPath.filter(function (x) { return x !== ''; });
        return trimmedPath;
    };
    // Parts from any query parameters in the URL
    RelatedPagesService.prototype.splitQueryParams = function (urlObject) {
        var groupedParams = Array.from(urlObject.searchParams.entries());
        var flattenedParams = groupedParams.flat();
        var splitParams = flattenedParams.flatMap(function (str) { return str.split(URL_SPLIT_REGEX); });
        return splitParams;
    };
    return RelatedPagesService;
}());


;// CONCATENATED MODULE: ./src/feedback-module-service.ts
var feedback_module_service_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var feedback_module_service_generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};

var FeedbackModuleService = /** @class */ (function () {
    function FeedbackModuleService(cid, eid, searchApiUrl, intranet, siteKey) {
        this.customerId = cid;
        this.engineId = eid;
        this.searchApiUrlPublic = searchApiUrl;
        this.isIntranet = intranet;
        this.authorizationKey = HttpService.getAuthorizationKey(cid, eid, siteKey);
    }
    FeedbackModuleService.prototype.sendFeedback = function (customerId, engineId, feedbackData) {
        return feedback_module_service_awaiter(this, void 0, void 0, function () {
            var baseUrl, requestUrl, e_1;
            return feedback_module_service_generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        baseUrl = HttpService.getBaseUrlForCustomer(customerId, 4);
                        requestUrl = baseUrl + "/".concat(customerId, "/").concat(engineId, "/feedback");
                        _a.label = 1;
                    case 1:
                        _a.trys.push([1, 3, , 4]);
                        return [4 /*yield*/, HttpService.postWithFetch(requestUrl, feedbackData, {
                                isIntranet: false,
                                authorizationKey: HttpService.getAuthorizationKey(customerId, engineId, 'SearchKey'),
                                contentType: 'application/json'
                            })];
                    case 2:
                        _a.sent();
                        return [3 /*break*/, 4];
                    case 3:
                        e_1 = _a.sent();
                        console.error('CludoJS: Error fetching feedback module submit', e_1);
                        return [3 /*break*/, 4];
                    case 4: return [2 /*return*/];
                }
            });
        });
    };
    return FeedbackModuleService;
}());


;// CONCATENATED MODULE: ./src/cludo.ts
var cludo_awaiter = (undefined && undefined.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var cludo_generator = (undefined && undefined.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
















var NO_SEARCH_TERM_ELEM_ID = 'cludo-no-search-term';
var Cludo = /** @class */ (function () {
    //#endregion
    function Cludo(search) {
        var _a, _b;
        this.totalDocuments = 0;
        //#endregion
        //#region Client Template functions and properties
        this.autocompleteTemplateClient = autocompleteTemplateClient;
        this.richAutocompleteTemplateClient = richAutocompleteTemplateClient;
        this.standardAutocompleteTemplateClient = standardAutocompleteTemplateClient;
        this.prepareAutocompleteContainer = prepareAutocompleteContainer;
        this.searchResultTemplateClient = searchResultTemplateClient;
        this.onEndlessScrollResultsReturned = onEndlessScrollResultsReturned;
        this.errorTemplateClient = errorTemplateClient;
        this.clearStoredSearchResponseData = clearStoredSearchResponseData;
        this.mapClientSearchResponse = mapClientSearchResponse;
        this.clearStoredAutocompleteResponseData = clearStoredAutocompleteResponseData;
        this.autocompleteRestoreClient = autocompleteRestoreClient;
        this.autocompleteKeyboardSelectionChange = autocompleteKeyboardSelectionChange;
        this.autocompleteSetSelectedSuggestion = autocompleteSetSelectedSuggestion;
        this.autocompleteSetSelectedResult = autocompleteSetSelectedResult;
        this.clientTemplateBeforeSearch = clientTemplateBeforeSearch;
        this.clientTemplatePrepareResultContainer = clientTemplatePrepareResultContainer;
        this.setInstantSuggestionsClient = setInstantSuggestionsClient;
        this.getAutocompleteSuggestionsFromInstantSuggestions = getAutocompleteSuggestionsFromInstantSuggestions;
        this.autocompleteSetSelectedRecentSearch = autocompleteSetSelectedRecentSearch;
        this.setActiveDescendantToSuggestions = setActiveDescendantToSuggestions;
        this.setClientTemplateComponentsController = setClientTemplateComponentsController;
        // put the instance in an array of Cludo instances
        window.CludoSearchInstances = window.CludoSearchInstances || [];
        window.CludoSearchInstances.push(this);
        // helpers declaration
        this.helpers = new Helpers();
        // translate declaration
        this.translateProvider = new TranslateProvider();
        // mandatory settings
        this.customerId = search.customerId;
        this.engineId = typeof search.engineId !== 'undefined' ? search.engineId : search.siteId;
        this.experienceId = search.experienceId || null;
        this.searchUrl = search.searchUrl;
        // Optional settings
        //   set the default api url based on customer id.
        this.defaultApiUrl = HttpService.getBaseUrlForCustomer(this.customerId);
        this.searchApiUrl = typeof search.searchApiUrl !== 'undefined' ? search.searchApiUrl : this.defaultApiUrl;
        // force default values to use core api host.
        // this.searchApiUrl = (search.searchApiUrl === "https://api-eu1.cludo.com/api/v3" || search.searchApiUrl === "https://api.cludo.com/api/v3") ? this.defaultApiUrl : this.searchApiUrl;
        this.searchApiUrlPublic = typeof search.searchApiUrlPublic !== 'undefined' ? search.searchApiUrlPublic : this.defaultApiUrl;
        this.statisticsApiUrl = typeof search.statisticsApiUrl !== 'undefined' ? search.statisticsApiUrl : 'https://stat.cludo.com';
        this.logPageVisits = typeof search.logPageVisits !== 'undefined' ? search.logPageVisits : true;
        this.searchSiteKey = typeof search.searchSiteKey !== 'undefined' ? search.searchSiteKey : 'SearchKey';
        this.intranetSearch = typeof search.intranetSearch !== 'undefined' ? search.intranetSearch : false;
        this.customHttpHeaders = typeof search.customHttpHeaders !== 'undefined' ? search.customHttpHeaders : {};
        this.customerTemplate = typeof search.customerTemplate !== 'undefined' ? search.customerTemplate : 'SearchContent';
        this.disableAutocomplete = typeof search.disableAutocomplete !== 'undefined' ? search.disableAutocomplete : false;
        this.richAutocomplete = typeof search.richAutocomplete !== 'undefined' ? search.richAutocomplete : false;
        this.autocompleteForceUseTemplate = typeof search.autocompleteForceUseTemplate !== 'undefined' ? search.autocompleteForceUseTemplate : false;
        this.autocompleteMinimumQueryLength = typeof search.autocompleteMinimumQueryLength !== 'undefined' ? search.autocompleteMinimumQueryLength : 1;
        this.facets = {};
        this.facetsOption = typeof search.facets !== 'undefined' ? search.facets : [];
        this.applyMultiLevelFacets = typeof search.applyMultiLevelFacets !== 'undefined' ? search.applyMultiLevelFacets : true;
        this.initFacets = typeof search.initFacets !== 'undefined' ? search.initFacets : null;
        this.filters = typeof search.filters !== 'undefined' ? search.filters : {};
        this.sortOrder = typeof search.sortOrder !== 'undefined' ? search.sortOrder : {};
        this.rangeFacets = typeof search.rangeFacets !== 'undefined' ? search.rangeFacets : {};
        this.searchInputs = typeof search.searchInputs !== 'undefined' ? search.searchInputs : ["cludo-search-form"];
        this.pierceShadowDom = typeof search.pierceShadowDom !== 'undefined' ? search.pierceShadowDom : false;
        this.perPage = typeof search.perPage !== 'undefined' ? search.perPage : null;
        this.enableRelatedSearches = typeof search.enableRelatedSearches !== 'undefined' ? search.enableRelatedSearches : false;
        this.bannerIsInSearchTemplate = typeof search.bannerIsInSearchTemplate !== 'undefined' ? search.bannerIsInSearchTemplate : true;
        this.xhrRequestHeader = typeof search.xhrRequestHeader !== 'undefined' ? search.xhrRequestHeader : "application/json";
        this.searchResultsWrapper = typeof search.searchResultsWrapper !== 'undefined' ? search.searchResultsWrapper : 'cludo-search-results';
        this.translateProvider.language = typeof search.language !== 'undefined' ? search.language : (typeof this.filters.Language !== 'undefined' ? this.filters.Language[0] : 'da');
        this.initSearchBoxText = typeof search.initSearchBoxText !== 'undefined' ? search.initSearchBoxText : '';
        this.loadingHTML = typeof search.loading != 'undefined' ? search.loading : '<img src="https://customer.cludo.com/img/loading.gif" class="loading" tabindex="-1" alt="loading search results" />';
        this.changeWindowLocation = typeof search.changeWindowLocation != 'undefined' ? search.changeWindowLocation : true;
        this.hideResultsCount = typeof search.hideResultsCount !== 'undefined' ? search.hideResultsCount : false;
        this.hideSearchFilters = typeof search.hideSearchFilters !== 'undefined' ? search.hideSearchFilters : false;
        this.hideSearchDidYouMean = typeof search.hideSearchDidYouMean !== 'undefined' ? search.hideSearchDidYouMean : false;
        //To be used when customer wants to show facets from other categories, when there are no results for currently selected caegory
        //Default value is true (facets always hidden if there ar no result)
        this.hideSearchFiltersIfNoResult = typeof search.hideSearchFiltersIfNoResult !== 'undefined' ? search.hideSearchFiltersIfNoResult : true;
        this.customNoResultsMessage = typeof search.customNoResultsMessage !== 'undefined' ? search.customNoResultsMessage : null;
        this.resetFiltersBeforeSearch = typeof search.resetFiltersBeforeSearch !== 'undefined' ? search.resetFiltersBeforeSearch : false;
        this.resetSortBeforeSearch = typeof search.resetSortBeforeSearch !== 'undefined' ? search.resetSortBeforeSearch : false;
        this.updateInputOnBlur = typeof search.updateInputOnBlur !== 'undefined' ? search.updateInputOnBlur : true;
        // Voice Search
        this.enableVoiceSearch = typeof search.enableVoiceSearch !== 'undefined' ? search.enableVoiceSearch : false;
        this.disableVoiceSearchActiveAnimation = typeof search.disableVoiceSearchActiveAnimation !== 'undefined' ? search.disableVoiceSearchActiveAnimation : false;
        this.voiceGrammar = typeof search.voiceGrammar !== 'undefined' ? search.voiceGrammar : [];
        // Show fixed Query results by default.
        this.useFixedQueryInResultsCount = typeof search.useFixedQueryInResultsCount !== 'undefined' ? search.useFixedQueryInResultsCount : true;
        this.allowSearchWithoutSearchword = typeof search.allowSearchWithoutSearchword !== 'undefined' ? search.allowSearchWithoutSearchword : false;
        this.jumpToTopOnFacetClick = typeof search.jumpToTopOnFacetClick !== 'undefined' ? search.jumpToTopOnFacetClick : true;
        //Endless scroll
        this.endlessScroll = typeof search.endlessScroll !== 'undefined' ? search.endlessScroll : null;
        this.endlessScrollElements = { scrolledElement: null, documentElement: null, backToTop: null, loadMore: null };
        // Use this to toggle the image tracking.
        this.enableExtendedTrackingRef = { value: true };
        this.enableExtendedTracking = typeof search.enableExtendedTracking !== 'undefined' ? search.enableExtendedTracking : true;
        //custom callback function after results loaded
        this.customCallbackAfterSearch = typeof search.customCallbackAfterSearch !== 'undefined' ? search.customCallbackAfterSearch : null;
        this.customCallbackBeforeSearch = typeof search.customCallbackBeforeSearch !== 'undefined' ? search.customCallbackBeforeSearch : null;
        this.customCallbackBeforeRedirect = typeof search.customCallbackBeforeRedirect !== 'undefined' ? search.customCallbackBeforeRedirect : null;
        //custom callback function after autocomplete
        this.customCallbackAfterAutocomplete = typeof search.customCallbackAfterAutocomplete !== 'undefined' ? search.customCallbackAfterAutocomplete : null;
        //custom callback function before quicklink
        this.customCallbackBeforeQuicklink = typeof search.customCallbackBeforeQuicklink !== 'undefined' ? search.customCallbackBeforeQuicklink : null;
        //custom callback for user tracking
        this.canUserBeTracked = typeof search.canUserBeTracked !== 'undefined' ? search.canUserBeTracked : null;
        //isTrackedSession tracks the ongoing value for whether or not session tracking is unknown, explicitly disallowed, or explicitly allowed (-1 | 0 | 1 respectively)
        this.isTrackedSession = -1;
        this.type = typeof search.type !== 'undefined' ? search.type : 'standard';
        // Client side templating
        this.clientTemplates = typeof search.clientTemplates !== 'undefined' ? search.clientTemplates : false;
        this.headlessSearch = typeof search.headlessSearch !== 'undefined' ? search.headlessSearch : false;
        // Only used when type == 'inline'.
        this.template = typeof search.template !== 'undefined' ? search.template : 'StandardInline';
        this.translateSearchTemplates = typeof search.translateSearchTemplates !== 'undefined' ? search.translateSearchTemplates : false;
        this.ovarlayResultsWrapperOpenClass = typeof search.ovarlayResultsWrapperOpenClass !== 'undefined' ? search.ovarlayResultsWrapperOpenClass : '';
        this.useStandardSearchTemplate = typeof search.useStandardSearchTemplate !== 'undefined' ? search.useStandardSearchTemplate : true;
        this.searchBoxPosition = typeof search.theme !== 'undefined' && typeof search.theme.searchBoxPosition !== 'undefined' ? search.theme.searchBoxPosition : { align: 'right', x: 20, y: 20 };
        this.themeColor = typeof search.theme !== 'undefined' && typeof search.theme.themeColor !== 'undefined' ? search.theme.themeColor : '';
        this.elementFocusColor = typeof search.theme !== 'undefined' && typeof search.theme.elementFocusColor !== 'undefined' ? search.theme.elementFocusColor : '';
        this.themeBannerColor = typeof search.theme !== 'undefined' && typeof search.theme.themeBannerColor !== 'undefined' ? search.theme.themeBannerColor : null;
        this.borderRadius = typeof search.theme !== 'undefined' && typeof search.theme.borderRadius !== 'undefined' ? search.theme.borderRadius : 0;
        this.borderRadiusInput = typeof search.theme !== 'undefined' && typeof search.theme.borderRadiusInput !== 'undefined' ? search.theme.borderRadiusInput : 0;
        this.showSearchPage = typeof search.showSearchPage !== 'undefined' ? search.showSearchPage : true;
        this.paramsPrefix = typeof search.paramsPrefix !== 'undefined' ? search.paramsPrefix : 'cludo';
        this.clientTemplateSortOptions = typeof search.sortOptions !== 'undefined' ? search.sortOptions : [];
        // Accessibility
        this.focusOnResultsAfterSearch = typeof search.focusOnResultsAfterSearch !== 'undefined' ? search.focusOnResultsAfterSearch : false;
        this.isSearchAfterRedirect = false;
        // Services
        this.storageService = new StorageService(this.paramsPrefix, this.engineId || "EX".concat(this.experienceId)); // add prefix to the experience ID to prevent the possibility of a clash between engine ID and experience ID
        this.conversationService = new ConversationService(this.storageService);
        this.trendingPagesService = new TrendingPagesService();
        this.relatedPagesService = new RelatedPagesService(this.customerId, this.engineId, this.searchApiUrl, this.intranetSearch, this.searchSiteKey);
        this.feedbackService = new FeedbackModuleService(this.customerId, this.engineId, this.searchApiUrl, this.intranetSearch, this.searchSiteKey);
        // link to text fragments
        this.linkFragment = '';
        // Alternate list delimiter instead of comma in URL. 
        this.urlListDelimiter = allowedUrlListDelimiters.includes(search.urlListDelimiter) ? search.urlListDelimiter : ',';
        // Alternate name to use for GTM data layer. 
        this.gtmDataLayerName = (_a = search.gtmDataLayerName) !== null && _a !== void 0 ? _a : 'dataLayer';
        // Make tracking wait for specific event before we emit our GTM events
        this.waitForGtmEvent = (_b = search.waitForGtmEvent) !== null && _b !== void 0 ? _b : null;
        this.isLoadingResults = false;
        // This flag will make the autocomplete box persist. Set this in the console for easier styling.
        this.debug = false;
        // Enable instant suggestions i.e. Suggested Searches and Recent Searches
        this.showInstantSuggestions = typeof search.showInstantSuggestions !== 'undefined' ? search.showInstantSuggestions : false;
        // Provide custom headers to Suggested/Recent Searches
        this.suggestedSearchesHeader = typeof search.suggestedSearchesHeader !== 'undefined' ? search.suggestedSearchesHeader : null;
        this.recentSearchesHeader = typeof search.recentSearchesHeader !== 'undefined' ? search.recentSearchesHeader : null;
        // Limit the Recent Searches to show
        this.recentSearchLimit = 5;
        this.recentSearches = [];
        // Check for a specific Google Analytics tracking ID to send search events
        this.googleAnalyticsTrackingId = typeof search.googleAnalyticsTrackingId !== 'undefined' ? search.googleAnalyticsTrackingId : null;
        this.authorizationKey = '';
        this.websiteSettings = typeof search.publicSettings !== 'undefined' ? search.publicSettings : {};
        /** In-memory session ID, used when tracking or cookies are disabled */
        this.localSessionId = '';
        this.sessionExpiration = 1800000; //30 minutes
        this.inputTypeVoiceKey = "voice";
        this.inputTypeStandardKey = "standard";
        this.lastQuery = null;
        this.querySessionId = null;
        // preserve init sort order
        this.initSortOrder = this.helpers.cloneObject(this.sortOrder);
        this.params = {
            ResponseType: (this.clientTemplates) ? "JsonObject" : "JsonHtml",
            Template: this.customerTemplate,
            facets: {},
            filters: this.filters,
            page: 1,
            query: '',
            text: '',
            traits: [],
            sort: this.sortOrder,
            rangeFacets: this.rangeFacets,
            perPage: this.perPage,
            enableRelatedSearches: this.enableRelatedSearches,
            applyMultiLevelFacets: this.applyMultiLevelFacets
        };
        this.autocompleteParamDefaultValue = "off";
        this.searchInputsLength = 0;
        this.searchComponentsDictionary = {};
        this.searchComponentsKeys = [];
        this.lastModifiedSearchComponent = null;
        this.activeAutocompleteFilters;
        this.elemSearchResults = {
            results: null,
            pagination: null,
            filters: null,
            relatedSearches: null,
            didYouMean: null,
            resultCount: null,
            banner: null
        };
        this.elemAutocomplete = {
            lists: [],
            listsItems: []
        };
        this.didYouMean = '';
        this.totalDocuments = 0;
        this.fixedQuery = null;
        this.responseTime = null;
        this.autocompleteResponseData = null;
        this.selectedIndex = -1;
        this.isSearchResultPage = false;
        this.autocompleteDebounceTimerId = null;
        this.hideAutocomplete = false;
        this.pendingAcTitle = null;
        this.pendingAcIndex = null;
        this.lastAcQuery = null;
        this.quicklink = null;
        this.isOverlaySearch = false;
        this.overlaySearchFormWrapperId = 'cludo-search-form-content';
        // Obsolete however leaving here and continuing to set in case some external javascript relies on this
        this.openedOverlayOnInit = false;
        this.elemOverlaySearch = {
            closeButton: null,
            overlay: null,
            overlayInner: null,
            overlayHeader: null,
            overlayBody: null,
            overlayFooter: null,
            searchWrapper: null,
            searchBox: null,
            searchBoxLabel: null,
            searchBoxInput: null,
            searchBoxButton: null,
            searchBoxContent: null,
            searchBoxContentLabel: null,
            searchBoxContentInput: null,
            searchBoxContentButton: null,
            poweredBy: null,
            poweredByMobile: null
        };
        this.isLazyLoading = false;
        this.doSearchWithDelayTimer = null;
        this.referalHostName = location.hostname;
        this.deviceType = null;
        this.inputType = null;
        // compatibility variables
        this.browserIsIE = window.navigator.userAgent.indexOf('MSIE') > 0;
        this.browserIsEdge14 = typeof window.navigator.appVersion !== 'undefined' && window.navigator.appVersion.indexOf('Edge/14') > 0;
        //accessibility
        this.userIsUsingTabulator = false;
        this.resultItemCurrentlyFocusedElement = null;
        this.resetFocusTimerPoweredBy = null;
        this.enabledFeatures = [];
        this.autoCompleteIsLoading = false;
        //static endpoint variables. These exist in case customers need to manually override them.
        this.autoCompleteControllerAction = "Autocomplete";
        this.publicSettingsRetrieved = (Object.keys(this.websiteSettings).length) ? true : false;
        this.pageInitFromBackForward = false;
        // Initialize values for detailed event tracking
        this.initSearchMetadata();
        // Initialize stored search response and autocomplete data
        this.clearStoredSearchResponseData();
        this.clearStoredAutocompleteResponseData();
        this.bindEventHandlers();
        if (window.performance && window.performance.getEntriesByType) {
            var perfEntries = window.performance.getEntriesByType("navigation");
            for (var i = 0; i < perfEntries.length; i++) {
                var perfEntryItem = perfEntries[i];
                if (perfEntryItem instanceof PerformanceNavigationTiming) {
                    var navigationType = perfEntryItem.type;
                    if (navigationType === 'back_forward') {
                        this.pageInitFromBackForward = true;
                        break;
                    }
                }
            }
        }
    }
    Object.defineProperty(Cludo.prototype, "loading", {
        get: function () {
            return this.loadingHTML;
        },
        //#region Getters/Setters
        set: function (value) {
            this.loadingHTML = value;
        },
        enumerable: false,
        configurable: true
    });
    Object.defineProperty(Cludo.prototype, "enableExtendedTracking", {
        get: function () {
            return this.enableExtendedTrackingRef.value;
        },
        set: function (value) {
            this.enableExtendedTrackingRef.value = value;
        },
        enumerable: false,
        configurable: true
    });
    Object.defineProperty(Cludo.prototype, "storedAutocompleteResponse", {
        // Represents the data for the current autocomplete response
        // FUTURE -- track isLoading
        //        -- add maxSuggestions/Results to config values
        get: function () {
            return {
                cludoAutocompleteResponse: {
                    query: this.autocompleteResponseData.query,
                    facets: this.autocompleteResponseData.Facets,
                    totalResults: this.autocompleteResponseData.TotalResults,
                    totalSuggestions: this.autocompleteResponseData.TotalSuggestions,
                    totalRecentSearches: this.storedRecentSearchesClient.length,
                    results: this.autocompleteResponseData.Results.slice(0, 5),
                    suggestions: this.autocompleteResponseData.Suggestions.slice(0, 5),
                    instantSuggestions: this.autocompleteResponseData.InstantSuggestions,
                    recentSearches: this.storedRecentSearchesClient,
                    topHits: this.autocompleteResponseData.TopHits
                },
                isLoading: this.autoCompleteIsLoading,
            };
        },
        enumerable: false,
        configurable: true
    });
    Cludo.prototype.init = function () {
        var _this = this;
        this.initTrackedSession();
        this.isOverlaySearch = this.isSearchWithOverlay();
        if (this.isOverlaySearch && this.type !== 'customOverlay') {
            this.endlessScroll = { stopAfterPage: 3, resultsPerPage: 10, bottomOffset: 50 };
            this.endlessScrollElements = { scrolledElement: null, documentElement: null, backToTop: null, loadMore: null };
            if (this.useStandardSearchTemplate) {
                this.params['overlay'] = 'Standard' + this.translateProvider.language;
            }
            if (this.type === 'standardOverlayWithDynamicSearchBox') {
                this.overlaySetTopSearchBox();
            }
            if (this.themeColor !== '' || this.borderRadius !== 0) {
                this.overlaySetColorTheme();
            }
        }
        else if (this.type === 'inline') {
            // Support old version where we internationalize by template
            if (this.template === 'facets' || this.template === 'noFacets' || this.template === 'nofacets') {
                this.params['overlay'] = this.template + this.translateProvider.language;
                if (this.template === "noFacets" || this.template === "nofacets") {
                    this.hideSearchFilters = true;
                }
            }
            else {
                // if template is NOT facets or noFacets then we're using I18N templates
                this.translateSearchTemplates = true;
                this.params['overlay'] = this.template + 'I18N';
            }
        }
        this.initSearchFormElements();
        this.deviceType = this.getDeviceType();
        // all inputs box should be recognized at the begining
        this.setIsSearchResultPage();
        if ((!this.isOverlaySearch && this.isSearchResultPage) || (this.isOverlaySearch && this.type == 'customOverlay')) {
            //set search results for business search on init or for cutom overlay (standard search get seperate call to that method, when overlay is opened)
            this.setResultElements();
        }
        this.setLoadingElements();
        this.setFacets();
        this.setInitParams();
        if (this.elemSearchResults.results != null && !this.isOverlaySearch) {
            this.getWebsiteSettings();
        }
        if (this.isSearchResultPage && this.endlessScroll) {
            if (this.endlessScroll.scrolledElementSelector) {
                var element = document.querySelector(this.endlessScroll.scrolledElementSelector);
                this.endlessScrollElements.scrolledElement = this.endlessScrollElements.documentElement = element;
            }
            else if (!this.isOverlaySearch) {
                this.endlessScrollElements.scrolledElement = window;
                this.endlessScrollElements.documentElement = document.documentElement;
            }
            else if (this.isOverlaySearch && this.type == 'customOverlay') {
                this.endlessScrollElements.scrolledElement = this.endlessScrollElements.documentElement = this.getResultWrapperContainer();
            }
            // use perPage if set, otherwise use endlessScroll settings
            if (this.perPage) {
                this.endlessScroll.resultsPerPage = this.perPage;
            }
            else if (this.endlessScroll.resultsPerPage) {
                this.params.perPage = this.perPage = this.endlessScroll.resultsPerPage;
            }
            this.endlessScrollAddScrollEvent();
            var resultsWrapper = this.getResultWrapperContainer();
            if (resultsWrapper) {
                this.endlessScrollSetElements(resultsWrapper);
            }
        }
        this.processSearchOnLoadOrStateChange();
        // Add history event handling on pages where we render search results
        if ((this.isSearchResultPage || this.isOverlaySearch) && this.browserSupportsHistoryApi()) {
            window.addEventListener('popstate', function (event) {
                // Processing a previously used search state (either through back or forward in browser)
                if (event.state && event.state.searchParams) {
                    if (_this.paramObjectsAreDifferent(event.state.searchParams, _this.params)) {
                        _this.params = event.state.searchParams;
                        _this.processSearchOnLoadOrStateChange();
                    }
                }
                // Processing a new search where we have not attached the search state
                else if (!event.state || !event.state.processed) {
                    // we should be here if this is a new, unprocessed search
                    _this.updateCludoHistoryState(event.state, _this.params);
                }
            });
        }
    };
    /**
     * Update the history state with the current search params
     * @param baseState
     * @param searchParams
     */
    Cludo.prototype.updateCludoHistoryState = function (baseState, searchParams) {
        var state = (baseState) ? baseState : {};
        state.processed = true;
        if (searchParams) {
            state.searchParams = searchParams;
        }
        history.replaceState(state, '');
    };
    Cludo.prototype.browserSupportsHistoryApi = function () {
        if (window.history) {
            return true;
        }
        return false;
    };
    /** Bind `this` on all event handlers so that we can reference other class properties and avoid
     *  creating duplicate event listeners.
     */
    Cludo.prototype.bindEventHandlers = function () {
        this.searchBoxInputFocusEvent = this.searchBoxInputFocusEvent.bind(this);
        this.searchBoxInputBlurEvent = this.searchBoxInputBlurEvent.bind(this);
        this.searchBoxInputEvent = this.searchBoxInputEvent.bind(this);
        this.searchBoxInputKeydownEvent = this.searchBoxInputKeydownEvent.bind(this);
        this.searchBoxClickEvent = this.searchBoxClickEvent.bind(this);
        this.searchBoxClearClickEvent = this.searchBoxClearClickEvent.bind(this);
        this.searchVoiceButtonClickEvent = this.searchVoiceButtonClickEvent.bind(this);
        this.searchBoxWrapperBlurEvent = this.searchBoxWrapperBlurEvent.bind(this);
        this.searchResultKeyUpEvent = this.searchResultKeyUpEvent.bind(this);
        this.searchResultTrackClickEventHandler = this.searchResultTrackClickEventHandler.bind(this);
        this.autocompleteMouseOverEvent = this.autocompleteMouseOverEvent.bind(this);
        this.autocompleteMouseDownEvent = this.autocompleteMouseDownEvent.bind(this);
        this.poweredByKeyupEvent = this.poweredByKeyupEvent.bind(this);
        this.closeButtonClickEvent = this.closeButtonClickEvent.bind(this);
        this.closeButtonKeyupEvent = this.closeButtonKeyupEvent.bind(this);
        this.closeButtonWindowKeyupEvent = this.closeButtonWindowKeyupEvent.bind(this);
        this.endlessScrollLoadMoreClickEvent = this.endlessScrollLoadMoreClickEvent.bind(this);
        this.endlessScrollBackToTopClickEvent = this.endlessScrollBackToTopClickEvent.bind(this);
        this.endlessScrollBackToTopKeyupEvent = this.endlessScrollBackToTopKeyupEvent.bind(this);
        this.endlessScrollScrollEvent = this.endlessScrollScrollEvent.bind(this);
        this.limitSearchOnHashchange = this.limitSearchOnHashchange.bind(this);
        this.limitSearchOnload = this.limitSearchOnload.bind(this);
    };
    /**
     * Checks if the two objects are different according to Cludo search requirements. It takes into account
     * one special state where we do not want to treat page changes as different for endless scroll.
     * @param {string} poppedParams
     * @param {string} currentParams
     * @returns true if the two params are different
     */
    Cludo.prototype.paramObjectsAreDifferent = function (poppedParams, currentParams) {
        var paramKeys = [
            'facets',
            'filters',
            'query',
            'sort',
            'rangeFacets'
        ];
        if (!this.endlessScroll) {
            paramKeys.push('page');
        }
        for (var i = 0; i < paramKeys.length; i++) {
            var paramKey = paramKeys[i];
            if (!poppedParams[paramKey] && !currentParams[paramKey]) {
                continue;
            }
            else if (!poppedParams[paramKey] || !currentParams[paramKey]) {
                return true;
            }
            var stateValue1 = JSON.stringify(poppedParams[paramKey]);
            var stateValue2 = JSON.stringify(currentParams[paramKey]);
            if (stateValue1 != stateValue2) {
                return true;
            }
        }
        return false;
    };
    /**
     * Process the searchInputs and creates search comopnents objects containing all elements related to a Cludo search form (wrapper, input, search button, search clear button)
     */
    Cludo.prototype.initSearchFormElements = function () {
        if (!this.searchInputs || this.searchInputs.length == 0) {
            if (!this.headlessSearch) {
                console.error('CludoJs Error: Missing search input configuration during initialization');
            }
            return;
        }
        // popolute search form components objects from searchInputs
        for (var i = 0; i < this.searchInputs.length; i++) {
            var searchInputIdOrQuerySelector = this.searchInputs[i];
            this.registerSearchFormElement(searchInputIdOrQuerySelector, this.pierceShadowDom);
        }
        if (this.searchInputsLength === 0 && !this.headlessSearch) {
            console.log('CludoJs Warning: No search inputs were found during initialization');
        }
    };
    // returns true if we registered new elements
    Cludo.prototype.registerSearchFormElement = function (searchInputIdOrQuerySelector, pierceShadowDom, parentElement) {
        parentElement = parentElement ? parentElement : document;
        // ============================
        // Try process as an element id; continue loop if we match
        var searchInputWrapper = this.helpers.getElementById(searchInputIdOrQuerySelector, pierceShadowDom, parentElement);
        // Will flip to true if we end up finding at least one. Using a query selector can register multiple which is why we care about finding at least one.
        var foundAtLeastOneSearchComponent = false;
        if (searchInputWrapper) {
            foundAtLeastOneSearchComponent = this.addSearchFormComponentFromWrapper(searchInputIdOrQuerySelector, searchInputWrapper, pierceShadowDom) || foundAtLeastOneSearchComponent;
        }
        else {
            // ===============================
            // Try process as a query selector
            var matchingElements = this.helpers.querySelectorAll(searchInputIdOrQuerySelector, pierceShadowDom, parentElement);
            for (var j = 0; j < matchingElements.length; j++) {
                var matchingElement = matchingElements[j];
                // Add index to lookup to add uniqueness when selector matches multiple elements
                var inputFormLookupKey = searchInputIdOrQuerySelector + ':' + j;
                foundAtLeastOneSearchComponent = this.addSearchFormComponentFromWrapper(inputFormLookupKey, matchingElement, pierceShadowDom) || foundAtLeastOneSearchComponent;
            }
        }
        return foundAtLeastOneSearchComponent;
    };
    /**
     * This method finds and builds a search component object containing wrapper, input, search button, clear button, and facet scope
     * @param inputWrapper Wrapper containing all search input elements
     */
    Cludo.prototype.buildSearchComponentsObjectFromWrapper = function (inputWrapper, pierceShadowDom) {
        if (!inputWrapper) {
            return null;
        }
        var searchComponentsObject = {
            wrapper: inputWrapper,
            searchBoxInput: undefined,
            searchBoxButton: undefined,
            searchBoxClearButton: undefined,
            searchBoxFacets: undefined,
            voiceSearchButton: undefined
        };
        // populate searchBoxInput
        var searchBoxInput = (this.helpers.querySelectorAll('input[type=text]', pierceShadowDom, inputWrapper)[0] ||
            this.helpers.querySelectorAll('input[type=search]', pierceShadowDom, inputWrapper)[0]);
        if (searchBoxInput) {
            searchComponentsObject.searchBoxInput = searchBoxInput;
            var autocompleteValue = searchBoxInput.getAttribute('autocomplete');
            if (!autocompleteValue) {
                searchBoxInput.setAttribute('autocomplete', this.autocompleteParamDefaultValue);
            }
        }
        // populate searchBoxButton
        searchComponentsObject.searchBoxButton = (this.helpers.querySelectorAll('button[type="submit"]', this.pierceShadowDom, inputWrapper)[0] ||
            this.helpers.querySelectorAll('button', this.pierceShadowDom, inputWrapper)[0] ||
            this.helpers.querySelectorAll('input[type=submit]', this.pierceShadowDom, inputWrapper)[0] ||
            this.helpers.querySelectorAll('input[type=image]', this.pierceShadowDom, inputWrapper)[0]);
        // populate searchBoxClearEvent
        searchComponentsObject.searchBoxClearButton = this.helpers.querySelectorAll('.cludo-search-query-clear', this.pierceShadowDom, inputWrapper)[0];
        // populate searchBoxFacets
        var hiddenInputs = this.helpers.querySelectorAll('input[type=hidden][data-facet][data-facet-name]', this.pierceShadowDom, inputWrapper);
        if (hiddenInputs.length > 0) {
            searchComponentsObject.searchBoxFacets = {};
            for (var i = 0; i < hiddenInputs.length; i++) {
                var hiddenInput = hiddenInputs[i];
                var facetName = hiddenInput.getAttribute("data-facet-name");
                var facetValue = hiddenInput.getAttribute("data-facet");
                if (facetName === '' || facetValue === '') {
                    continue;
                }
                if (!searchComponentsObject.searchBoxFacets[facetName]) {
                    searchComponentsObject.searchBoxFacets[facetName] = [];
                }
                searchComponentsObject.searchBoxFacets[facetName].push(facetValue);
            }
        }
        // if enabled, populate voice search box
        if (this.enableVoiceSearch && 'webkitSpeechRecognition' in window) {
            this.helpers.addButtonElement(inputWrapper, 'cludo-voice-icon', null, '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" \
                    x="0" y="0" \
                    viewBox="0 0 93.44 134.88" \
                ><g> \
                    <path stroke-width="0" \
                        d="M 50.04 100.45 V 124.56 C 50.04 126.39 48.55 127.88 46.72 127.88 C 44.89 127.88 43.4 126.39 43.4 124.56 V 100.45 C 33.24 99.64 24.08 95.15 17.26 88.33 C 9.69 80.77 5 70.34 5 58.87 C 5 57.04 6.49 55.55 8.32 55.55 S 11.64 57.04 11.64 58.87 C 11.64 68.51 15.59 77.28 21.95 83.64 C 28.31 90 37.08 93.95 46.72 93.95 H 46.72 C 56.36 93.95 65.13 90 71.49 83.64 C 77.85 77.28 81.8 68.51 81.8 58.87 C 81.8 57.04 83.29 55.55 85.12 55.55 S 88.44 57.04 88.44 58.87 C 88.44 70.35 83.75 80.78 76.19 88.34 C 69.36 95.16 60.2 99.64 50.04 100.45 L 50.04 100.45 Z M 46.94 5 C 53.32 5 59.12 7.61 63.32 11.81 C 67.52 16.01 70.13 21.81 70.13 28.19 V 58.19 C 70.13 64.57 67.52 70.37 63.32 74.57 C 59.12 78.77 53.32 81.38 46.94 81.38 S 34.76 78.77 30.56 74.57 C 26.36 70.37 23.75 64.57 23.75 58.19 V 28.19 C 23.75 21.81 26.36 16.01 30.56 11.81 C 34.76 7.61 40.56 5 46.94 5 L 46.94 5 Z M 58.62 16.51 C 55.62 13.51 51.48 11.65 46.94 11.65 C 42.39 11.65 38.26 13.51 35.26 16.51 C 32.26 19.51 30.4 23.65 30.4 28.19 V 58.19 C 30.4 62.74 32.26 66.87 35.26 69.87 C 38.26 72.87 42.4 74.73 46.94 74.73 C 51.49 74.73 55.62 72.87 58.62 69.87 C 61.62 66.87 63.48 62.73 63.48 58.19 V 28.19 C 63.49 23.64 61.62 19.51 58.62 16.51 L 58.62 16.51 Z" \
                    /> \
                </g></svg>', null, this.translateProvider.translate("voice_search_title"));
            if (!this.disableVoiceSearchActiveAnimation) {
                var css = "\
                    .cludo-voice-active svg { \
                        animation: voice-active-pulse 1s ease-in 0s infinite; \
                    } \
                    @keyframes voice-active-pulse { \
                        0% { \
                            opacity: 1; \
                        } \
                        50% { \
                            opacity: 0; \
                        } \
                        100% {\
                            opacity: 1; \
                        } \
                    }";
                this.helpers.addCssStyles(css);
            }
            // register new element w/ search components object
            searchComponentsObject.voiceSearchButton = this.helpers.querySelectorAll('.cludo-voice-icon', pierceShadowDom, inputWrapper)[0];
        }
        return searchComponentsObject;
    };
    /**
     * Build out search form component from wrapper element and added it to the model
     * @param {string} lookupKey Unique key for the search component
     * @param {HTMLElement} inputFormElement Wrapper element containing all search components for a search input
     */
    Cludo.prototype.addSearchFormComponentFromWrapper = function (lookupKey, inputFormElement, pierceShadowDom) {
        if (this.hasSearchComponentForKey(lookupKey)) {
            console.log('CludoJs Warning: CludoJs tried to register a search input more than once {' + lookupKey + '}');
            return false;
        }
        var searchComponentsObject = this.buildSearchComponentsObjectFromWrapper(inputFormElement, pierceShadowDom);
        if (!searchComponentsObject) {
            return false;
        }
        this.addSearchComponentsObject(lookupKey, searchComponentsObject);
        // subscribe to events
        if (searchComponentsObject.wrapper !== null) {
            this.searchBoxWrapperEvents(searchComponentsObject.wrapper);
            if (this.isOverlaySearch) {
                this.helpers.addClass(searchComponentsObject.wrapper, "cludo-search_autocomplete");
            }
        }
        if (searchComponentsObject.searchBoxInput != null) {
            this.searchBoxInputEvents(searchComponentsObject.searchBoxInput);
        }
        if (searchComponentsObject.searchBoxButton != null) {
            this.searchBoxEvents(searchComponentsObject.searchBoxButton);
        }
        if (searchComponentsObject.searchBoxClearButton != null) {
            this.searchBoxClearEvents(searchComponentsObject.searchBoxClearButton);
        }
        if (searchComponentsObject.voiceSearchButton != null) {
            this.searchBoxVoiceEvents(searchComponentsObject.voiceSearchButton);
        }
        return true;
    };
    /**
     * Add search component object to the dictionary
     * @param {string} lookupKey Unique key for the search component
     * @param {object} searchFormComponentsObject Search component object
     */
    Cludo.prototype.addSearchComponentsObject = function (lookupKey, searchFormComponentsObject) {
        this.searchComponentsKeys.push(lookupKey);
        this.searchComponentsDictionary[lookupKey] = searchFormComponentsObject;
        this.searchInputsLength = this.searchComponentsKeys.length;
    };
    Cludo.prototype.removeSearchComponentsObject = function (lookupKey) {
        var keyIndex = this.searchComponentsKeys.indexOf(lookupKey);
        if (keyIndex != -1) {
            this.searchComponentsKeys.splice(keyIndex, 1);
        }
        delete this.searchComponentsDictionary[lookupKey];
        this.searchInputsLength = this.searchComponentsKeys.length;
    };
    Cludo.prototype.hasSearchComponentForKey = function (lookupKey) {
        if (!this.searchComponentsDictionary[lookupKey]) {
            return false;
        }
        return true;
    };
    // search component object getters
    /**
     *
     * @param {string} lookupKey Unique key for the search component
     */
    Cludo.prototype.getSearchComponentsObject = function (lookupKey) {
        if (!this.searchComponentsDictionary[lookupKey]) {
            console.log('CludoJs Warning: CludoJs tried to retrieve a missing search components object');
            // return shell object to avoid null ref exception by consumer
            return this.getSearchComponentsShellObject();
        }
        return this.searchComponentsDictionary[lookupKey];
    };
    /**
     * Get all search component objects
     * @returns {SearchComponentsObject[]} Array of search component objects
     */
    Cludo.prototype.getSearchComponentsArray = function () {
        var searchComponentsArray = [];
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var searchComponentsKey = this.searchComponentsKeys[i];
            searchComponentsArray.push(this.getSearchComponentsObject(searchComponentsKey));
        }
        return searchComponentsArray;
    };
    Cludo.prototype.getSearchComponentsObjectFromSearchInputElement = function (inputElement) {
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var searchComponentsKey = this.searchComponentsKeys[i];
            var searchComponents = this.getSearchComponentsObject(searchComponentsKey);
            if (searchComponents.searchBoxInput == inputElement) {
                return searchComponents;
            }
        }
        console.log('CludoJs Warning: CludoJs could not resolve search component from input element');
        return this.getSearchComponentsShellObject();
    };
    Cludo.prototype.getSearchComponentsObjectFromSearchBoxButton = function (searchButtonElement) {
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var searchComponentsKey = this.searchComponentsKeys[i];
            if (this.getSearchComponentsObject(searchComponentsKey).searchBoxButton == searchButtonElement) {
                return this.getSearchComponentsObject(searchComponentsKey);
            }
        }
        console.log('CludoJs Warning: CludoJs could not resolve search component from search box button');
        return this.getSearchComponentsShellObject();
    };
    Cludo.prototype.getSearchComponentsObjectFromSearchBoxClearButton = function (clearButtonElement) {
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var searchComponentsKey = this.searchComponentsKeys[i];
            if (this.getSearchComponentsObject(searchComponentsKey).searchBoxClearButton == clearButtonElement) {
                return this.getSearchComponentsObject(searchComponentsKey);
            }
        }
        console.log('CludoJs Warning: CludoJs could not resolve search component from search clear button');
        return this.getSearchComponentsShellObject();
    };
    /** @returns the SearchComponentsObject associated w/ the passed voice button element */
    Cludo.prototype.getSearchComponentsObjectFromSearchVoiceButton = function (voiceButtonElement) {
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var searchComponentsKey = this.searchComponentsKeys[i];
            if (this.getSearchComponentsObject(searchComponentsKey).voiceSearchButton == voiceButtonElement) {
                return this.getSearchComponentsObject(searchComponentsKey);
            }
        }
    };
    /**
     * This retrieves the search components object associated with an autocomplete container. It assumes that
     * we place the autocomplete container adjacent to the autocomplete UL which is true today. We could
     * consider refactoring this to be more resilient in case that were to change in the future.
     * @param {HTMLUlElement} acEle - The autocomplete container
     */
    Cludo.prototype.getSearchComponentsObjectFromAutocompleteElement = function (acEle) {
        var acContainer = acEle.parentElement;
        // populate ac children for easier lookup in the upcoming code
        var acContainerChildren = [];
        for (var i = 0; i < acContainer.children.length; i++) {
            acContainerChildren.push(acContainer.children[i]);
        }
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var searchComponentsKey = this.searchComponentsKeys[i];
            var searchComponents = this.getSearchComponentsObject(searchComponentsKey);
            if (acContainerChildren.indexOf(searchComponents.searchBoxInput) != -1) {
                return searchComponents;
            }
        }
        console.log('CludoJs Warning: CludoJs could not resolve search component from search clear button');
        return this.getSearchComponentsShellObject();
    };
    Cludo.prototype.getSearchComponentsShellObject = function () {
        return {
            wrapper: undefined,
            searchBoxInput: undefined,
            searchBoxButton: undefined,
            searchBoxClearButton: undefined,
            searchBoxFacets: undefined,
            voiceSearchButton: undefined
        };
    };
    Cludo.prototype.initTrackedSession = function () {
        try {
            // grab whether session can be tracked from the StorageService
            this.isTrackedSession = this.storageService.getTrackingStatus();
        }
        catch (err) {
            this.isTrackedSession = -1;
        }
    };
    Cludo.prototype.updateIsTrackedSession = function () {
        // check for customer-defined callback
        if (!this.canUserBeTracked) {
            return;
        }
        // wrap in try catch just in case there's an error on the callback
        try {
            var localCanBeTracked = -1;
            var userCanBeTrackedResponse = this.canUserBeTracked();
            if (userCanBeTrackedResponse === true) {
                localCanBeTracked = 1;
            }
            else if (userCanBeTrackedResponse === false) {
                localCanBeTracked = 0;
            }
            if (localCanBeTracked === this.isTrackedSession) {
                return;
            }
            this.isTrackedSession = localCanBeTracked;
            // by this point, something is different. we need to update storage
            if (this.isTrackedSession === 1) {
                this.enableTrackingForUser();
            }
            else if (this.isTrackedSession === 0) {
                this.disableTrackingForUser();
            }
        }
        catch (err) {
            //
        }
    };
    Cludo.prototype.logPageVisit = function () {
        if (!this.logPageVisits)
            return;
        try {
            var params = {
                url: location.href,
                eid: this.engineId,
                cid: this.customerId
            };
            var queryString = this.helpers.objectToQueryString(params);
            var elemDiv = document.createElement('img');
            elemDiv.src = this.statisticsApiUrl + '/__ctm.gif?' + queryString;
            elemDiv.style.display = "none";
            document.body.appendChild(elemDiv);
        }
        catch (err) {
            //Ignore
        }
    };
    // SETTERS
    // Merge pre-set autocomplete filters with general filters into active autocomplete filters object
    /**
     * searchBoxFacets is the collection on the search component object
     */
    Cludo.prototype.setAutocompleteFilters = function (searchBoxFacets) {
        var merged = {};
        for (var cur in this.filters) {
            merged[cur] = this.filters[cur];
        }
        for (var cur in searchBoxFacets) {
            merged[cur] = searchBoxFacets[cur];
        }
        this.activeAutocompleteFilters = merged;
    };
    Cludo.prototype.setResultElements = function () {
        this.resultsWrapper = this.getResultWrapperContainer();
        if (this.resultsWrapper != null) {
            if (this.resultsWrapper.querySelector(".search-result-count") === null
                && !this.hideResultsCount && !this.clientTemplates) {
                this.helpers.addElement(this.resultsWrapper, "search-result-count");
            }
            if (this.resultsWrapper.querySelector(".search-did-you-mean") === null
                && !this.hideSearchDidYouMean && !this.clientTemplates) {
                this.helpers.addElement(this.resultsWrapper, "search-did-you-mean", '', "complementary");
            }
            if (this.resultsWrapper.querySelector(".search-results") === null) {
                this.helpers.addElement(this.resultsWrapper, "search-results");
            }
            if (this.resultsWrapper.querySelector(".search-filters") === null && !this.hideSearchFilters) {
                this.helpers.addElement(this.resultsWrapper, "search-filters");
            }
            if (this.resultsWrapper.querySelector(".search-related") === null && this.enableRelatedSearches) {
                this.helpers.addElement(this.resultsWrapper, "search-related");
            }
            this.elemSearchResults = this.getSearchResultsElements();
            this.addAccessibilityAttributesToSearchResultsElements(this.elemSearchResults);
        }
    };
    Cludo.prototype.addAccessibilityAttributesToSearchResultsElements = function (elemSearchResults) {
        // Add Role=status to search count if one is not already defined
        if (elemSearchResults.resultCount != null && !elemSearchResults.resultCount.hasAttribute("role")) {
            elemSearchResults.resultCount.setAttribute("role", "status");
        }
        // Add aria-live = polite to results container
        if (elemSearchResults.results != null && !elemSearchResults.results.hasAttribute("aria-live")) {
            elemSearchResults.results.setAttribute("aria-live", "polite");
        }
        // Set role=navigation and aria-live=polite to filters
        if (elemSearchResults.filters !== null && elemSearchResults.filters.length > 0) {
            elemSearchResults.filters.forEach(function (filter) {
                if (!filter.hasAttribute("role")) {
                    filter.setAttribute("role", "navigation");
                }
                if (!filter.hasAttribute("aria-live")) {
                    filter.setAttribute("aria-live", "polite");
                }
            });
        }
    };
    Cludo.prototype.setLoadingElements = function () {
        if (this.isOverlaySearch && this.type !== 'customOverlay') {
            this.loadingHTML = '<div id="cludo-loading"><div id="loading_1" class="loading">Loading</div><div id="loading_2" class="loading">Loading</div></div>';
        }
        else {
            this.loadingHTML = '<div id="cludo-loading">' + this.loadingHTML + '</div>';
        }
    };
    // Wrapper to get the container
    Cludo.prototype.getResultWrapperContainer = function () {
        // first try to get it as an element id
        var searchResultWrapper = document.getElementById(this.searchResultsWrapper);
        if (searchResultWrapper) {
            return searchResultWrapper;
        }
        // now lets try as a selector
        return document.querySelector(this.searchResultsWrapper);
    };
    // get search result object which contains the results, counts, did you mean and filters
    Cludo.prototype.getSearchResultsElements = function () {
        var resultsWrapper = this.getResultWrapperContainer();
        return {
            results: resultsWrapper.querySelector(".search-results"),
            resultCount: this.hideResultsCount ? null : resultsWrapper.querySelector(".search-result-count"),
            didYouMean: this.hideSearchDidYouMean ? null : resultsWrapper.querySelector(".search-did-you-mean"),
            filters: this.hideSearchFilters ? null : Array.from(resultsWrapper.querySelectorAll(".search-filters")),
            banner: !this.bannerIsInSearchTemplate ? resultsWrapper.querySelector(".search-banner") : null,
            relatedSearches: this.enableRelatedSearches ? Array.from(resultsWrapper.querySelectorAll('.search-related')) : null
        };
    };
    Cludo.prototype.setIsSearchResultPage = function () {
        // THIS BLOCK IS TEMPORARY UNTIL 10000068 implements the workaround
        if (this.customerId == 10000068) {
            if (this.helpers.getWindowLocation().indexOf(this.searchUrl) > -1) {
                this.isSearchResultPage = true;
            }
            else {
                this.isSearchResultPage = false;
            }
            return;
        }
        var currentUrl = this.helpers.getWindowLocation();
        // handle special cases
        if (this.searchUrl == '' || this.searchUrl == '/') {
            this.isSearchResultPage = true;
        }
        else if (currentUrl.indexOf(this.searchUrl) > -1) {
            var everythingAfterSearchUrl = this.getEverythingAfterSearchUrlButBeforeQueryParameters();
            // After all normalizations, if there's still a slash in everythingAfter, it
            // means we have a complex, nested url and is not the page we're on
            if (everythingAfterSearchUrl.indexOf('/') != -1) {
                this.isSearchResultPage = false;
                return;
            }
            // If everythingAfter is falsy or if it begins with 'index', we assume
            // the current page is the same as the searchUrl
            if (!everythingAfterSearchUrl || everythingAfterSearchUrl.indexOf('index') == 0) {
                this.isSearchResultPage = true;
                return;
            }
            this.isSearchResultPage = false;
        }
    };
    Cludo.prototype.getEverythingAfterSearchUrlButBeforeQueryParameters = function () {
        var currentUrl = this.helpers.getWindowLocation();
        var everythingAfter = currentUrl.substring(currentUrl.indexOf(this.searchUrl) + (this.searchUrl).length);
        // Normalize the string by removing a leading slash if it exists
        // We do this because some web servers do not distinguish some-path and some-path/
        if (everythingAfter.indexOf('/') == 0) {
            everythingAfter = everythingAfter.substr(1);
        }
        // If we have a hash or a question mark, let's ignore them
        everythingAfter = everythingAfter.split('?')[0];
        everythingAfter = everythingAfter.split('#')[0];
        return everythingAfter;
    };
    Cludo.prototype.getWebsiteSettings = function (searchInputElement) {
        var _this = this;
        if (!this.helpers.isEmpty(this.websiteSettings)) {
            this.configureFeaturesFromPublicSettings(this.websiteSettings, searchInputElement);
        }
        // Build the authorization key if we haven't already
        if (!this.intranetSearch && !this.authorizationKey) {
            this.authorizationKey = HttpService.getAuthorizationKey(this.customerId, this.engineId, this.searchSiteKey);
        }
        // Make the request
        Cludo.getPublicSettings(this.customerId, this.engineId, this.searchApiUrl, this.authorizationKey, this.searchSiteKey, this.intranetSearch, this.customHttpHeaders).then(function (data) {
            _this.httpSuccessCallback(data, "settingsTemplate", searchInputElement, _this.params.query);
        }, function () {
            _this.httpFailureCallback("settingsTemplate");
        });
    };
    /** Static method for getting public settings */
    // leaving here in order to support backwards compatibility with early versions of search components implementations
    Cludo.getPublicSettings = function (customerId, engineId, apiUrl, authKey, searchSiteKey, isIntranet, customHeaders) {
        if (searchSiteKey === void 0) { searchSiteKey = 'SearchKey'; }
        if (isIntranet === void 0) { isIntranet = false; }
        if (customHeaders === void 0) { customHeaders = {}; }
        return SettingsService.getPublicSettingsByEngine(customerId, engineId, apiUrl, authKey, searchSiteKey, isIntranet, customHeaders);
    };
    /**
     * Get public settings
     */
    Cludo.getPublicSettingsByOptions = function (options) {
        var customerId = options.customerId, engineId = options.engineId, experienceId = options.experienceId, apiUrl = options.apiUrl, authKey = options.authKey, searchSiteKey = options.searchSiteKey, isIntranet = options.isIntranet;
        if (!customerId || (!engineId && !experienceId)) {
            throw new Error('CludoJs Error: customerId and either engineId or experienceId are required');
        }
        if (experienceId) {
            return SettingsService.getPublicSettingsByExperience(customerId, engineId, experienceId, apiUrl, authKey, searchSiteKey, isIntranet);
        }
        else {
            return SettingsService.getPublicSettingsByEngine(customerId, engineId, apiUrl, authKey, searchSiteKey, isIntranet);
        }
    };
    Cludo.prototype.getAuthorizationKey = function () {
        var key = this.customerId + ":" + this.engineId + ":" + this.searchSiteKey;
        var base64key = window.btoa(key);
        return base64key;
    };
    /** If the customer attempts to use a feature that is not in their subscription, override the corresponding setting */
    Cludo.prototype.toggleSettingsForEnabledFeatures = function () {
        if (this.enableVoiceSearch && this.enabledFeatures.indexOf("voice search") === -1) {
            this.disableVoiceSearch();
        }
        if (this.showInstantSuggestions && this.enabledFeatures.indexOf("instant suggestions") === -1) {
            this.disablePresuggestions();
        }
    };
    /** Disable Instant Suggestions (Popular and Recent Searches) */
    Cludo.prototype.disablePresuggestions = function () {
        this.showInstantSuggestions = false;
    };
    /** Removes voice buttons from all search inputs */
    Cludo.prototype.disableVoiceSearch = function () {
        var _a;
        this.enableVoiceSearch = false;
        for (var i = 0; i < this.searchComponentsKeys.length; i++) {
            var key = this.searchComponentsKeys[i];
            var voiceButton = this.searchComponentsDictionary[key].voiceSearchButton;
            (_a = voiceButton.parentNode) === null || _a === void 0 ? void 0 : _a.removeChild(voiceButton);
            this.searchComponentsDictionary[key].voiceSearchButton = null;
        }
    };
    /** Initializes `this.facets` and assigns the value to `this.params.facets` */
    Cludo.prototype.setFacets = function () {
        var _this = this;
        // If facetsOption isn't passed, assign a default value to facets
        if (!this.facetsOption.length) {
            this.facets = { "Category": [] };
            // Build facets from initFacets, if supplied
            if (this.initFacets !== null) {
                for (var key in this.facets) {
                    if (typeof this.initFacets[key] !== 'undefined') {
                        this.facets[key] = this.initFacets[key];
                    }
                    else {
                        this.facets[key] = [];
                    }
                }
            }
        }
        else {
            // If there's a url param for facets, don't use initFacets
            var setInitFacet_1 = true;
            this.facetsOption.forEach(function (facet) {
                if (_this.helpers.getURLParam(_this.getQueryParameterVariableName(facet)) != '') {
                    setInitFacet_1 = false;
                }
            });
            // Build facets from facetsOption & initFacets (if applicable)
            this.facetsOption.forEach(function (facet) {
                var facetValue = [];
                if (_this.initFacets !== null && setInitFacet_1) {
                    facetValue = typeof _this.initFacets[facet] !== 'undefined' ? _this.initFacets[facet] : [];
                }
                _this.facets[facet] = facetValue;
            });
        }
        // Set property in search params
        this.params.facets = this.facets;
    };
    Cludo.prototype.setInitParams = function () {
        if (!this.intranetSearch) {
            this.authorizationKey = HttpService.getAuthorizationKey(this.customerId, this.engineId, this.searchSiteKey);
        }
        this.params.query = this.getQueryFromUrl();
        // did it come from an ac?
        this.pendingAcTitle = this._getReferralAcTitle();
        this.pendingAcIndex = this._getReferralAcIndex();
        this.showSearchPage = this.helpers.getURLParam(this.getQueryParameterVariableName("showsearchpage")) === "false" ? false : this.showSearchPage;
        if ((!this.queryIsNullOrEmpty() || this.allowSearchWithoutSearchword) && (this.isSearchResultPage || this.isOverlaySearch)) {
            this.params.page = this.helpers.getURLParam(this.getQueryParameterVariableName("page")) != '' ? parseInt(this.helpers.getURLParam(this.getQueryParameterVariableName("page"))) : 1;
            this.inputType = this.helpers.getURLParam(this.getQueryParameterVariableName("inputtype")) != '' ? this.helpers.getURLParam(this.getQueryParameterVariableName("inputtype")) : this.inputTypeStandardKey;
            if (this.showSearchPage) {
                for (var facet in this.params.facets) {
                    var value = this.helpers.getURLParam(this.getQueryParameterVariableName(facet), true);
                    if (value != '') {
                        var facetValues = [];
                        var facetValuesRaw = value.split(this.urlListDelimiter);
                        for (var fi = 0; fi < facetValuesRaw.length; fi++) {
                            facetValues.push(this.helpers.stripHtmlTags(decodeURIComponent(facetValuesRaw[fi])));
                        }
                        this.params.facets[facet] = facetValues;
                    }
                }
                for (var filter in this.params.filters) {
                    var value = this.helpers.getURLParam(this.getQueryParameterVariableName(filter));
                    if (value != '') {
                        var filterValues = value.split(this.urlListDelimiter);
                        this.params.filters[filter] = filterValues;
                    }
                }
                var sortRaw = this.helpers.getURLParam(this.getQueryParameterVariableName("sort"), true);
                if (sortRaw != '') {
                    var sortItems = sortRaw.split(this.urlListDelimiter);
                    for (var si = 0; si < sortItems.length; si++) {
                        var sort = decodeURIComponent(sortItems[si]).split('=');
                        this.params.sort[sort[0]] = sort[1];
                    }
                }
                if (this.isOverlaySearch && this.params.query !== '') {
                    this.openedOverlayOnInit = true;
                    this.overlayOpenModalWithSearch();
                }
                this.isSearchAfterRedirect = true;
            }
        }
    };
    Cludo.prototype.setElementValue = function (element, value) {
        if (element != null && value != "*") {
            element.value = value;
        }
    };
    /**
     * @param {object[]} searchBoxFacets The search box facets that come from the search component
     */
    Cludo.prototype.setFacetsBeforeSearch = function (searchBoxFacets) {
        this.params.page = 1;
        if (typeof searchBoxFacets != 'undefined' && !this.helpers.isEmpty(searchBoxFacets)) {
            for (var key in searchBoxFacets) {
                this.facets[key] = [];
                this.facets[key] = searchBoxFacets[key];
            }
        }
        else {
            if (this.initFacets !== null) {
                for (var key in this.facets) {
                    if (typeof this.initFacets[key] !== 'undefined') {
                        this.facets[key] = this.initFacets[key];
                    }
                    else {
                        this.facets[key] = [];
                    }
                }
                this.params.facets = this.facets;
            }
            else {
                for (var key in this.facets) {
                    this.facets[key] = [];
                }
            }
        }
    };
    Cludo.prototype.processSearchOnLoadOrStateChange = function () {
        if ((!this.queryIsNullOrEmpty() || this.allowSearchWithoutSearchword) &&
            (this.isSearchResultPage || this.isOverlaySearch) &&
            this.showSearchPage) {
            for (var i = 0, len = this.searchInputsLength; i < len; i++) {
                var searchComponents = this.getSearchComponentsObject(this.searchComponentsKeys[i]);
                this.setElementValue(searchComponents.searchBoxInput, this.params.query);
                if (searchComponents.searchBoxClearButton != null && this.params.query !== "") {
                    this.helpers.removeClass(searchComponents.searchBoxClearButton, 'cludo-hidden');
                }
            }
            this.isSearchAfterRedirect = true;
            this.facets = this.params.facets;
            // wait until search time before setting history state
            if (this.browserSupportsHistoryApi()) {
                this.updateCludoHistoryState(history.state, (this.isSearchAfterRedirect) ? this.params : null);
            }
            // Reinitialize overlay modal before calling into doSearch
            if (this.isOverlaySearch && !this.isSearchResultPage) {
                this.overlayOpenModalWithSearch();
            }
            if (this.endlessScroll) {
                this.doSearchWithDelay(1, this.params.page);
            }
            else {
                this.doSearch();
            }
        }
    };
    // SEARCH BOX EVENT HANDLERS
    Cludo.prototype.searchBoxInputEvents = function (element) {
        element.addEventListener("focus", this.searchBoxInputFocusEvent, true);
        element.addEventListener("blur", this.searchBoxInputBlurEvent, true);
        element.addEventListener("input", this.searchBoxInputEvent, true);
        element.addEventListener("keydown", this.searchBoxInputKeydownEvent, true);
    };
    Cludo.prototype.searchBoxEvents = function (element) {
        element.addEventListener("click", this.searchBoxClickEvent, true);
    };
    Cludo.prototype.searchBoxClearEvents = function (element) {
        element.addEventListener("click", this.searchBoxClearClickEvent, true);
    };
    Cludo.prototype.searchBoxVoiceEvents = function (element) {
        element.addEventListener('click', this.searchVoiceButtonClickEvent, true);
    };
    Cludo.prototype.searchBoxWrapperEvents = function (element) {
        element.addEventListener("blur", this.searchBoxWrapperBlurEvent, true);
    };
    Cludo.prototype.searchBoxWrapperBlurEvent = function (event) {
        var target = event.currentTarget || event.srcElement;
        if (!(target instanceof Element)) {
            return;
        }
        // ensure that we don't treat clicking in the autocomplete box as a real "blur" event
        var autocompleteContainerId = '#search_autocomplete';
        var autocompleteContainer = target.querySelector(autocompleteContainerId);
        if (autocompleteContainer && autocompleteContainer.contains(event.relatedTarget)) {
            return;
        }
        var input = (target.querySelectorAll('input[type=text]')[0] || target.querySelectorAll('input[type=search]')[0]);
        if (input && this.updateInputOnBlur) {
            input.value = this.params.query === '' || this.params.query === '*' ? this.initSearchBoxText : this.params.query;
        }
        if (!this.disableAutocomplete) {
            this.autocompleteRestore();
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    Cludo.prototype.searchBoxInputFocusEvent = function (event) {
        var target = event.currentTarget || event.srcElement;
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        var searchBoxComponents = this.getSearchComponentsObjectFromSearchInputElement(target);
        var position = 0;
        // Check for pre-set filters on input and apply to active autocomplete filters
        if (searchBoxComponents.searchBoxFacets != null) {
            this.setAutocompleteFilters(searchBoxComponents.searchBoxFacets);
        }
        else {
            this.activeAutocompleteFilters = null;
        }
        if (!this.disableAutocomplete) {
            this.autocompleteRestore();
        }
        if (this.helpers.isEmpty(this.websiteSettings)) {
            this.getWebsiteSettings(target);
        }
        else if (this.showInstantSuggestions && target.value == "") {
            this.setInstantSuggestions(target);
        }
        target.value = target.value === this.initSearchBoxText ? '' : this.params.query;
        if (typeof target.selectionStart !== 'undefined') {
            position = target.selectionStart === 0 ? target.value.length : target.selectionStart;
        }
        if (typeof target.setSelectionRange !== 'undefined') {
            target.setSelectionRange(position, position);
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
        if (this.clientTemplates) {
            this.prepareAutocompleteContainer(target);
            this.clientTemplatesComponentController.processEvent('afterinputfocus');
        }
    };
    Cludo.prototype.searchBoxInputBlurEvent = function (event) {
        var target = event.currentTarget;
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        target.value = this.params.query === '' || this.params.query === '*' ? this.initSearchBoxText : this.params.query;
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    Cludo.prototype.searchBoxInputEvent = function (e) {
        if (e) {
            this.handleSearchBoxInputChangeEvent(e);
        }
    };
    Cludo.prototype.handleSearchBoxInputChangeEvent = function (event) {
        var target = event.currentTarget;
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        var searchBoxComponents = this.getSearchComponentsObjectFromSearchInputElement(target);
        var keynum = this.helpers.getKey(event);
        this.params.query = this.helpers.stripHtmlTags(target.value);
        if (!this.disableAutocomplete && keynum != this.helpers.ENTER && keynum != this.helpers.DOWN && keynum != this.helpers.UP && keynum != this.helpers.ESC && keynum != this.helpers.TAB) {
            this.autocomplete(target);
        }
        else if (keynum === this.helpers.ESC) {
            if (this.isOverlaySearch && this.elemOverlaySearch.overlay) {
                this.overlayCloseModalWithSearch();
            }
            else if (!this.disableAutocomplete) {
                this.autocompleteRestore();
            }
        }
        // Show instant suggestions if the input is empty and we don't have a suggestion highlighted
        if (this.showInstantSuggestions && target.value == "" && this.selectedIndex === -1) {
            this.setInstantSuggestions(target);
        }
        if (typeof searchBoxComponents.searchBoxClearButton !== 'undefined') {
            if (this.params.query !== "") {
                this.helpers.removeClass(searchBoxComponents.searchBoxClearButton, 'cludo-hidden');
            }
            else {
                this.helpers.addClass(searchBoxComponents.searchBoxClearButton, 'cludo-hidden');
            }
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    Cludo.prototype.searchBoxInputKeydownEvent = function (event) {
        var target = event.currentTarget;
        var keynum = this.helpers.getKey(event);
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        // Register the last modified search component
        var searchComponents = this.getSearchComponentsObjectFromSearchInputElement(target);
        this.lastModifiedSearchComponent = searchComponents;
        // Check for pre-set filters on input and apply if the click event is ENTER
        if (searchComponents.searchBoxFacets != null && keynum === this.helpers.ENTER) {
            this.setFacetsBeforeSearch(searchComponents.searchBoxFacets);
        }
        this.hideAutocomplete = false;
        if (this.clientTemplates) {
            this.autocompleteKeyboardSelectionChange(keynum);
        }
        else {
            if (keynum === this.helpers.ENTER || keynum === this.helpers.DOWN || keynum === this.helpers.UP) {
                this.autocompleteKeyDownEvent(keynum, target, event);
            }
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    /**
     * Search box button click event handler
     * @param {Event} event
     */
    Cludo.prototype.searchBoxClickEvent = function (event) {
        var target = event.currentTarget;
        if (!(target instanceof Element)) {
            return;
        }
        var searchComponents = this.getSearchComponentsObjectFromSearchBoxButton(target);
        this.lastModifiedSearchComponent = searchComponents;
        if (!this.disableAutocomplete) {
            this.autocompleteRestore();
        }
        if (this._handleQuickLinks()) {
            if (event && event.preventDefault) {
                event.preventDefault();
            }
            if (event && event.stopPropagation) {
                event.stopPropagation();
            }
            else {
                event.cancelBubble = true;
            }
            return;
        }
        this.setFacetsBeforeSearch(searchComponents.searchBoxFacets);
        if (this.isOverlaySearch) {
            this.overlayOpenModalWithSearch();
        }
        if (this.resetFiltersBeforeSearch) {
            this.params.filters = {};
        }
        this.setInputTypeAndSearch(this.inputTypeStandardKey);
        if (event && event.preventDefault) {
            event.preventDefault();
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    Cludo.prototype.searchBoxClearClickEvent = function (event) {
        var target = event.currentTarget;
        if (!(target instanceof Element)) {
            return;
        }
        var searchComponents = this.getSearchComponentsObjectFromSearchBoxClearButton(target);
        searchComponents.searchBoxInput.value = "";
        this.params.query = "";
        if (this.elemSearchResults.banner) {
            this.elemSearchResults.banner.innerHTML = "";
        }
        if (this.elemSearchResults.didYouMean) {
            this.elemSearchResults.didYouMean.innerHTML = "";
        }
        if (this.elemSearchResults.filters) {
            for (var i = 0; i < this.elemSearchResults.filters.length; i++) {
                this.elemSearchResults.filters[i].innerHTML = "";
            }
        }
        if (this.elemSearchResults.relatedSearches) {
            for (var i = 0; i < this.elemSearchResults.relatedSearches.length; i++) {
                this.elemSearchResults.relatedSearches[i].innerHTML = "";
            }
        }
        if (this.elemSearchResults.resultCount) {
            this.elemSearchResults.resultCount.innerHTML = "";
        }
        if (this.elemSearchResults.results) {
            this.elemSearchResults.results.innerHTML = "";
            this.removeSearchInputAriaErrorAttributes();
        }
        if (this.endlessScrollElements.loadMore) {
            this.helpers.addClass(this.endlessScrollElements.loadMore, 'cludo-hidden');
        }
        if (this.endlessScrollElements.backToTop) {
            this.helpers.removeClass(this.endlessScrollElements.backToTop, 'cludo-opacity1');
            this.helpers.addClass(this.endlessScrollElements.backToTop, 'cludo-opacity0');
        }
        this.helpers.addClass(target, 'cludo-hidden');
        if (event && event.preventDefault) {
            event.preventDefault();
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    /** Click event for voice search button */
    Cludo.prototype.searchVoiceButtonClickEvent = function (event) {
        var _this = this;
        var target = event.currentTarget || event.srcElement;
        if (!(target instanceof Element)) {
            return;
        }
        var searchComponentsObj = this.getSearchComponentsObjectFromSearchVoiceButton(target);
        var currentSearchBox = searchComponentsObj.searchBoxInput;
        var placeholder = currentSearchBox.placeholder;
        // clear out the current query
        this.params.query = '';
        this.setElementValue(currentSearchBox, '');
        if ('webkitSpeechRecognition' in window && this.enableVoiceSearch) {
            var recognition_1 = new window.webkitSpeechRecognition();
            recognition_1.continuous = this.helpers.isBrowserSafari(); // avoid a weird bug on Safari by setting continuous to true (https://developer.apple.com/forums//thread/694847?answerId=731859022#731859022)
            recognition_1.interimResults = true;
            recognition_1.lang = this.translateProvider.language;
            // In case grammars eventually become supported, we will add the option here
            if (this.voiceGrammar.length && recognition_1.grammars) {
                var speechRecognitionList = this.helpers.buildRecognitionGrammar(this.voiceGrammar);
                recognition_1.grammars = speechRecognitionList;
            }
            recognition_1.start();
            var final_transcript_1 = '';
            var timeout_1; // set timeout to trigger speechend after certain amount of silence
            var initDelay_1 = 5000; // wait this long for initial voice input before canceling
            var continueDelay_1 = 2000; // wait this long for pauses in voice input before searching
            recognition_1.onstart = function () {
                // initiate timeout
                timeout_1 = window.setTimeout(function () {
                    _this.endSpeechAndSearch('', recognition_1, target, placeholder);
                }, initDelay_1);
                if (!target.classList.contains('cludo-voice-active')) {
                    target.classList.add('cludo-voice-active');
                }
            };
            recognition_1.onresult = function (event) {
                var interim_transcript = '';
                for (var i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        final_transcript_1 = event.results[i][0].transcript;
                        _this.endSpeechAndSearch(final_transcript_1, recognition_1, target, placeholder);
                    }
                    else {
                        interim_transcript += event.results[i][0].transcript;
                        currentSearchBox.placeholder = interim_transcript;
                        // speech started - overwrite initial timeout with continuous timeout
                        if (timeout_1) {
                            clearTimeout(timeout_1);
                        }
                        timeout_1 = window.setTimeout(function () {
                            _this.endSpeechAndSearch(interim_transcript, recognition_1, target, placeholder);
                        }, continueDelay_1);
                    }
                }
            };
            recognition_1.onspeechend = function () {
                target.classList.remove('cludo-voice-active');
                if (timeout_1) {
                    clearTimeout(timeout_1);
                }
            };
            recognition_1.onerror = function (event) {
                target.classList.remove('cludo-voice-active');
                if (timeout_1) {
                    clearTimeout(timeout_1);
                }
                // suppress warning for non-fatal 'abort' errors
                if (event.error !== 'aborted') {
                    console.error('CludoJS Error: Voice recognition failed: ', event);
                }
            };
        }
    };
    Cludo.prototype.endSpeechAndSearch = function (query, recognition, target, inputPlaceholder) {
        var searchComponentsObj = this.getSearchComponentsObjectFromSearchVoiceButton(target);
        var currentSearchBox = searchComponentsObj.searchBoxInput;
        if (query) {
            if (this.helpers.isBrowserSafari()) {
                query = this.helpers.removeDuplicateTranscript(query);
            }
            query = this.helpers.stripSpecialChars(query);
            this.params.query = query;
            currentSearchBox.placeholder = inputPlaceholder;
            this.setFacetsBeforeSearch(searchComponentsObj.searchBoxFacets);
            if (this.resetFiltersBeforeSearch) {
                this.params.filters = {};
            }
            if (this.isOverlaySearch) {
                this.overlayOpenModalWithSearch();
            }
            this.setElementValue(currentSearchBox, query);
            this.setInputTypeAndSearch(this.inputTypeVoiceKey);
        }
        recognition.stop();
        target.classList.remove('cludo-voice-active');
    };
    // SEARCH RESULTS EVENT HANDLER
    Cludo.prototype.searchResultsEvents = function () {
        this.registerClickTrackingEvents();
        this.didYouMeanEvents();
        this.searchFacetsEvents();
        this.paginationEvents();
        this.removeFocusOnMouseClick();
        this.registerRelatedSearchesClickEvents();
        this.facetAttributeEvents(this.elemSearchResults.results);
    };
    Cludo.prototype.registerRelatedSearchesClickEvents = function () {
        var _this = this;
        if (this.elemSearchResults.relatedSearches &&
            this.elemSearchResults.relatedSearches.length > 0 &&
            this.elemSearchResults.relatedSearches[0].querySelectorAll) {
            var relatedSearchesLinks = [];
            // Gather all related search links.
            for (var i = 0; i < this.elemSearchResults.relatedSearches.length; i++) {
                var currentRelatedSearchContainerLinks = this.elemSearchResults.relatedSearches[i].querySelectorAll("a");
                Array.prototype.push.apply(relatedSearchesLinks, currentRelatedSearchContainerLinks);
            }
            // Attach click event to every related search link.
            for (var i = 0; i < relatedSearchesLinks.length; i++) {
                var link = relatedSearchesLinks[i];
                link.addEventListener("click", function (e) {
                    e.preventDefault();
                    if (!(e.target instanceof Element)) {
                        return;
                    }
                    var rsDataAttr = e.target.attributes.getNamedItem("data-relatedsearch");
                    if (rsDataAttr) {
                        var value = rsDataAttr.value;
                        _this.params.query = value;
                        if (_this.elemOverlaySearch && _this.elemOverlaySearch.searchBoxContentInput) {
                            _this.elemOverlaySearch.searchBoxContentInput.value = value;
                        }
                        _this.setInputTypeAndSearch(_this.inputTypeStandardKey);
                        _this.trackRelatedSearchClickEventHandler();
                    }
                    return false;
                });
            }
        }
    };
    // search result events
    Cludo.prototype.registerClickTrackingEvents = function () {
        var _this = this;
        if (this.elemSearchResults.results.querySelectorAll) {
            var resultLinks = Array.prototype.slice.call(this.elemSearchResults.results.querySelectorAll("a"));
            var outsideBannersLinks = Array.prototype.slice.call(document.querySelectorAll("[data-cludo-banner-location=outside] a"));
            resultLinks = Array.prototype.concat.call(resultLinks, outsideBannersLinks);
            resultLinks.forEach(function (resultLink) { return _this.addAnchorAttributesAndListeners(resultLink); });
        }
    };
    /**
     *
     * @param {*} e Click event
     * @param {*} targetElement The element containing the cludo properties used in creating the log. Defaults to `e.currentTarget`
     */
    Cludo.prototype.searchResultTrackClickEventHandler = function (e, target) {
        var isNewWindowClick = false;
        if (e.ctrlKey || e.metaKey) {
            isNewWindowClick = true;
        }
        if (!target && e.currentTarget instanceof HTMLElement) {
            target = e.currentTarget;
        }
        // Check if the link has a target attribute of "_blank"
        var hasBlankAttribute = target && target instanceof HTMLAnchorElement && target.target === "_blank";
        var isOpeningNewWindow = isNewWindowClick || hasBlankAttribute;
        // only prevent default if it's not opening a new window -- we have to allow the browser to open a new window itself
        //  or web content highlighting won't work for links outside of the domain
        if (!isOpeningNewWindow) {
            e.preventDefault();
        }
        if (target) {
            this.trackClickEventHandler(target, isOpeningNewWindow);
        }
    };
    // DEPRECATED -- no longer used, but keeping for backwards compatibility w/ undocumented customer solutions
    Cludo.prototype.searchResultClickEvent = function (event) {
        var target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        var linkTarget = ((event.metaKey && this.helpers.isMac()) || (event.ctrlKey && !this.helpers.isMac())) ? "_blank" : target.target;
        target.setAttribute('target', linkTarget);
        if (linkTarget === "_blank") {
            target.setAttribute('rel', 'noopener'); // FYI setting rel="noopener" is a security best practice
        }
        this.trackClickEventHandler(target);
        if (event && event.preventDefault) {
            event.preventDefault();
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = true;
        }
    };
    Cludo.prototype.searchResultKeyUpEvent = function (event) {
        var target = event.currentTarget;
        var keynum = this.helpers.getKey(event);
        if (keynum === this.helpers.TAB) {
            this.resultItemCurrentlyFocusedElement = target;
            this.userIsUsingTabulator = true;
        }
        if (event && event.stopPropagation) {
            event.stopPropagation();
        }
        else {
            event.cancelBubble = false;
        }
    };
    // search results other components
    Cludo.prototype.searchFacetsEvents = function () {
        var _this = this;
        if (this.elemSearchResults.filters !== null) {
            var _loop_1 = function (j, l) {
                var filterContainerElement = this_1.elemSearchResults.filters[j];
                filterContainerElement.setAttribute('aria-label', this_1.translateProvider.translate("search_filters"));
                var filters = filterContainerElement.querySelectorAll('LI');
                var _loop_2 = function (i, len) {
                    var filterElement = filters[i];
                    var filterAnchorElement = filterElement.querySelector('a');
                    var ariaLabelText = this_1.translateProvider.translate("template_all_results");
                    if (filterAnchorElement) {
                        ariaLabelText = filterAnchorElement.getAttribute('data-facet');
                    }
                    // Set aria-label to the LI element
                    filterElement.setAttribute('aria-label', ariaLabelText);
                    filterElement.onclick = function (e) {
                        var target = e.target;
                        if (target instanceof Element && target.nodeName == "A") {
                            if (e && e.stopPropagation) {
                                e.stopPropagation();
                            }
                            if (e && e.preventDefault) {
                                e.preventDefault();
                            }
                            else {
                                e.returnValue = false;
                            }
                            var selector = filters[i].querySelector('a');
                            if (selector != null) {
                                var facetName = selector.getAttribute("data-facet-name") !== null ? selector.getAttribute("data-facet-name") : "Category";
                                var facetValue = selector.getAttribute("data-facet");
                                var multifacetValue = selector.getAttribute("data-multifacet") !== null ?
                                    (selector.getAttribute("data-multifacet") === "true") : false;
                                _this.facet(facetName, facetValue, multifacetValue);
                            }
                        }
                    };
                };
                for (var i = 0, len = filters.length; i < len; i++) {
                    _loop_2(i, len);
                }
            };
            var this_1 = this;
            for (var j = 0, l = this.elemSearchResults.filters.length; j < l; j++) {
                _loop_1(j, l);
            }
        }
    };
    Cludo.prototype.facetAttributeEvents = function (ele) {
        var _this = this;
        if (!ele) {
            return;
        }
        var facetLinks = ele.querySelectorAll('a[data-facet-name]');
        var _loop_3 = function (i) {
            var facetLink = facetLinks[i];
            facetLink.onclick = function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                var facetName = facetLink.getAttribute("data-facet-name") !== null ? facetLink.getAttribute("data-facet-name") : "Category";
                var facetValue = facetLink.getAttribute("data-facet");
                var multifacetValue = facetLink.getAttribute("data-multifacet") !== null ?
                    (facetLink.getAttribute("data-multifacet") === "true") : false;
                _this.facet(facetName, facetValue, multifacetValue);
            };
        };
        for (var i = 0; i < facetLinks.length; i++) {
            _loop_3(i);
        }
    };
    /**
     * Custom event handler function for serving links to search (links that contain #)
     * It'll be triggered from the template
     * @param elm: element
     */
    Cludo.prototype.linkToSearchClickEvent = function (elm) {
        var url = elm.getAttribute("href");
        var hasTargetParameter = elm.getAttribute("target") === "_blank";
        if (url && !hasTargetParameter) {
            LocationService.setLocation(url);
            LocationService.reload();
        }
    };
    Cludo.prototype.didYouMeanEvents = function () {
        var _this = this;
        if (this.elemSearchResults.didYouMean !== null) {
            var anchorElem = this.elemSearchResults.didYouMean.querySelector('a');
            if (anchorElem) {
                anchorElem.onclick = function (e) {
                    if (e && e.stopPropagation) {
                        e.stopPropagation();
                    }
                    else {
                        e.cancelBubble = true;
                    }
                    if (e && e.preventDefault) {
                        e.preventDefault();
                    }
                    else {
                        e.returnValue = false;
                    }
                    _this.setDidYouMean();
                };
            }
        }
    };
    Cludo.prototype.paginationEvents = function () {
        var _this = this;
        if (this.totalDocuments > 0) {
            var paginations = this.elemSearchResults.results.querySelectorAll(".search_page_list");
            for (var j = 0, len = paginations.length; j < len; j++) {
                var pagination = paginations[j].querySelectorAll('LI');
                var _loop_4 = function (i, l) {
                    var paginationItem = pagination[i];
                    paginationItem.onclick = function (e) {
                        if (e && e.stopPropagation) {
                            e.stopPropagation();
                        }
                        else {
                            e.cancelBubble = true;
                        }
                        if (e && e.preventDefault) {
                            e.preventDefault();
                        }
                        else {
                            e.returnValue = false;
                        }
                        if (paginationItem.querySelector('a') != null) {
                            var pageNo = paginationItem.querySelector('a').getAttribute("data-page");
                            if (_this.params.page < parseInt(pageNo)) {
                                _this.searchEventTriggerQueue.push('paginationNext');
                            }
                            else {
                                _this.searchEventTriggerQueue.push('paginationPrevious');
                            }
                            _this.page(pageNo, true);
                        }
                    };
                };
                for (var i = 0, l = pagination.length; i < l; i++) {
                    _loop_4(i, l);
                }
            }
        }
    };
    Cludo.prototype.removeFocusOnMouseClick = function () {
        if (document.querySelectorAll) {
            var wrapper = this.getResultWrapperContainer();
            if (!wrapper) {
                return;
            }
            var a = wrapper.querySelectorAll('a,button');
            var _loop_5 = function (j) {
                var focusableElement = a[j];
                focusableElement.onmousedown = function () {
                    focusableElement.blur(); // most browsers
                    focusableElement.style.outline = 'none'; // mozilla
                };
                focusableElement.onmouseup = function () {
                    focusableElement.blur(); // most browsers
                    focusableElement.style.outline = null; // mozilla
                };
            };
            for (var j = 0; j < a.length; j++) {
                _loop_5(j);
            }
        }
    };
    /** Debounced wrapper of the _autocompleteByQuery function
     *  This function exists for clients that can receive data / events via the processEvent flow (currently only cludo-search-components)
     */
    Cludo.prototype.autocompleteByQuery = function (query) {
        var _this = this;
        // Sanity check
        if (!this.clientTemplates) {
            console.log('CludoJs Error: Method is not supported');
            return;
        }
        var debouncedAutocompleteRequest = function () {
            clearTimeout(_this.autocompleteDebounceTimerId);
            _this._autocompleteByQuery(query);
        };
        clearTimeout(this.autocompleteDebounceTimerId);
        var baseDebounceDelay = 300; // FUTURE: Make this configurable
        var debounceDelay = query.length > 5 ? baseDebounceDelay : Math.floor(baseDebounceDelay * query.length / 8);
        // Set search param query to the passed query
        // This needs to be outside of the "debounce" logic, otherwise the value in the search box
        // will be inconsistenly updated
        this.params.query = query;
        // Emit event when the query changes, which should cause client templates to re-render
        this.clientTemplatesComponentController.processEvent('afterautocomplete');
        this.autocompleteDebounceTimerId = window.setTimeout(function () {
            debouncedAutocompleteRequest(); // Resolve the promise after the autocomplete request has completed
        }, debounceDelay);
    };
    /** Perform an autocomplete request for the passed query and update the stored autocomplete response data */
    Cludo.prototype._autocompleteByQuery = function (query) {
        var _this = this;
        // Sanity check
        if (!this.clientTemplates) {
            console.log('CludoJs Error: Method is not supported');
            return;
        }
        // Store previously set filters before using autocomplete filters
        var currentSetSearchFilters = this.params.filters;
        if (this.params.query !== '') {
            if (this.richAutocomplete) {
                this.richAutocompleteRequest().then(function (response) {
                    // If the query passed to the function doesn't match the current query, ignore the response
                    if (query !== _this.params.query) {
                        return;
                    }
                    _this.autocompleteResponseData = JSON.parse(response);
                    _this.autocompleteResponseData.query = _this.params.query;
                    // Emit event (causes client templates to re-render)
                    _this.clientTemplatesComponentController.processEvent('afterautocomplete');
                }, function (error) {
                    if ((error === null || error === void 0 ? void 0 : error.name) === 'AbortError') {
                        // Request was aborted - no need to throw an error
                        return;
                    }
                    console.error(error);
                });
                // Restore previously set filters
                this.params.filters = currentSetSearchFilters;
            }
            else {
                this.standardAutocompleteRequest().then(function (response) {
                    // If the query passed to the function doesn't match the current query, ignore the response
                    if (query !== _this.params.query) {
                        return;
                    }
                    var suggestions = JSON.parse(response);
                    _this.autocompleteResponseData = _this.deriveAutocompleteResponseDataFromSuggestionArray(suggestions, query);
                    // Emit event (causes client templates to re-render)
                    _this.clientTemplatesComponentController.processEvent('afterautocomplete');
                });
                // Restore previously set filters
                this.params.filters = currentSetSearchFilters;
            }
        }
        else {
            // Clear autocomplete response data, then emit event to re-render
            this.autocompleteResponseData = {
                Facets: null,
                QueryId: this.queryId,
                ResponseTime: null,
                SearchResult: '',
                TotalResults: 0,
                TotalSuggestions: 0,
                query: '',
                Suggestions: [],
                Results: [],
            };
            this.clientTemplatesComponentController.processEvent('afterautocomplete');
        }
    };
    /** Helper for resolving the standard autocomplete response to something search components expects */
    Cludo.prototype.deriveAutocompleteResponseDataFromSuggestionArray = function (suggestions, query) {
        return {
            query: query,
            Facets: null,
            QueryId: this.queryId,
            ResponseTime: null,
            SearchResult: '',
            TotalResults: 0,
            TotalSuggestions: suggestions.length,
            Suggestions: suggestions.map(function (suggestion) {
                var typedDocument = {
                    ResultIndex: null,
                    Sortings: null,
                    Score: null,
                    FieldNames: [
                        'Title'
                    ],
                    Fields: {
                        'Title': {
                            Field: 'Title',
                            Highlights: [],
                            IsArray: false,
                            Value: suggestion,
                            Values: [suggestion]
                        }
                    },
                };
                return typedDocument;
            }),
            Results: [],
        };
    };
    /** Perform the standard autocomplete request using the passed parameters and return the response */
    Cludo.prototype.standardAutocompleteRequest = function () {
        return cludo_awaiter(this, void 0, void 0, function () {
            var httpServiceUrl;
            return cludo_generator(this, function (_a) {
                httpServiceUrl = "".concat(this.searchApiUrl, "/").concat(this.customerId, "/").concat(this.engineId, "/").concat(this.autoCompleteControllerAction, "?text=").concat(encodeURIComponent(this.params.query));
                if (!this.helpers.isEmpty(this.params.filters)) {
                    if (typeof this.params.filters.DomainName !== 'undefined') {
                        httpServiceUrl += "&filters[DomainName]=" + encodeURIComponent(this.params.filters.DomainName.toString());
                    }
                    if (typeof this.params.filters.Language !== 'undefined') {
                        httpServiceUrl += "&languages=" + encodeURIComponent(this.params.filters.Language.toString());
                    }
                }
                if (this.params.enablesa === true) {
                    httpServiceUrl += "&enablesa=true";
                }
                return [2 /*return*/, HttpService.getWithFetch(httpServiceUrl, {
                        isIntranet: this.intranetSearch,
                        authorizationKey: this.authorizationKey,
                        contentType: 'application/json',
                        customHeaders: this.customHttpHeaders
                    })];
            });
        });
    };
    /** Perform the rich autocomplete request using the passed parameters and return the response */
    Cludo.prototype.richAutocompleteRequest = function () {
        return cludo_awaiter(this, void 0, void 0, function () {
            var httpServiceUrl;
            var _this = this;
            return cludo_generator(this, function (_a) {
                this.autoCompleteIsLoading = true;
                // Set active autocomplete filters
                if (this.activeAutocompleteFilters) {
                    this.params.filters = this.activeAutocompleteFilters;
                }
                if ('AbortController' in window) {
                    // Cancel any in-progress request
                    if (this.autocompleteAbortController) {
                        this.autocompleteAbortController.abort();
                    }
                    this.autocompleteAbortController = new AbortController();
                }
                httpServiceUrl = "".concat(this.searchApiUrl, "/").concat(this.customerId, "/").concat(this.engineId, "/").concat(this.autoCompleteControllerAction);
                this.params.text = this.params.query;
                return [2 /*return*/, HttpService.postWithFetch(httpServiceUrl, this.params, {
                        isIntranet: this.intranetSearch,
                        authorizationKey: this.authorizationKey,
                        contentType: 'application/json',
                        customHeaders: this.customHttpHeaders,
                        abortSignal: this.autocompleteAbortController.signal
                    }).then(function (res) {
                        _this.autocompleteAbortController = null;
                        _this.autoCompleteIsLoading = false;
                        return res;
                    })];
            });
        });
    };
    /**
     * Handles updates to the search query, and updates the autocomplete container by
     *  either clearing it (if the query is empty or shorter than the minimum length)
     *  or by calling autocompleteDoRequest to trigger a web service request to search,
     *  and then populate the autocomplete element with the response data
     * @param searchInputElement
     */
    Cludo.prototype.autocomplete = function (searchInputElement) {
        var queryLength = this.params.query.replace(/\s/g, '').length;
        // Skip autocomplete if null/undefined/0 queryLength or if it's shorter than the minimum
        // Since the default for autocompleteMinimumQueryLength is 1, this usually doesn't happen
        if (!queryLength || queryLength < this.autocompleteMinimumQueryLength) {
            this.autocompleteRestore();
            return;
        }
        if (queryLength <= 2) {
            // Always do a request for 1-2 characters
            this.autocompleteDebounceTimerId = null;
            this.autocompleteDoRequest(searchInputElement);
        }
        else if (queryLength) {
            // Perform highlighting of the current autocomplete results, if they exist.
            // Note that this performs highlighting on the last autocomplete response data synchronously,
            // and will perform highlighting on the next autocomplete response data following the response from
            // the request sent below
            if (this.autocompleteResponseData !== null) {
                this.autocompleteResponseData.query = this.params.query;
                this.clientTemplates ?
                    this.autocompleteTemplateClient(this.autocompleteResponseData, searchInputElement, true) :
                    this.autocompleteTemplate(this.autocompleteResponseData, searchInputElement, true);
            }
            // Perform autocomplete request (debouncing)
            this.debouncedAutocompleteRequest(searchInputElement, queryLength);
        }
    };
    /** Debounce wrapper of the autocomplete request function for Razor Templates */
    Cludo.prototype.debouncedAutocompleteRequest = function (element, queryLength) {
        var _this = this;
        var debouncedFunction = function () {
            clearTimeout(_this.autocompleteDebounceTimerId);
            _this.autocompleteDoRequest(element);
        };
        clearTimeout(this.autocompleteDebounceTimerId);
        var baseDebounceDelay = 300; // FUTURE: Make this configurable
        var debounceDelay = queryLength > 5 ? baseDebounceDelay : Math.floor(baseDebounceDelay * queryLength / 8);
        this.autocompleteDebounceTimerId = window.setTimeout(debouncedFunction, debounceDelay);
    };
    /**
     * Performs an autocomplete request using current search parameters
     * @param {HTMLElement} element The search input element
     */
    Cludo.prototype.autocompleteDoRequest = function (element) {
        var _this = this;
        var setFilters = this.params.filters;
        if (this.params.query !== '') {
            // ensure that we're sanitizing request query property before sending it
            this.params.query = this.helpers.removeUnsafeCharacters(this.params.query);
            this.lastAcQuery = this.params.query;
            if (this.richAutocomplete) {
                this.richAutocompleteRequest().then(function (response) {
                    if (_this.hideAutocomplete) {
                        return;
                    }
                    _this.autocompleteResponseData = JSON.parse(response);
                    _this.autocompleteResponseData.query = _this.params.query;
                    _this.clientTemplates ? _this.autocompleteTemplateClient(_this.autocompleteResponseData, element, false) : _this.autocompleteTemplate(_this.autocompleteResponseData, element, false);
                }, function (error) {
                    if ((error === null || error === void 0 ? void 0 : error.name) === 'AbortError') {
                        // Request was aborted - no need to throw an error
                        return;
                    }
                    console.error(error);
                });
                this.params.filters = setFilters;
            }
            else {
                this.standardAutocompleteRequest().then(function (response) {
                    if (_this.hideAutocomplete) {
                        return;
                    }
                    var suggestions = JSON.parse(response);
                    // FUTURE: This is a workaround for the fact that the autocomplete response differs between
                    // the standard and rich autocomplete requests
                    _this.autocompleteResponseData = _this.deriveAutocompleteResponseDataFromSuggestionArray(suggestions, _this.params.query);
                    _this.clientTemplates ? _this.autocompleteTemplateClient(_this.autocompleteResponseData, element, false) : _this.autocompleteTemplate(_this.autocompleteResponseData, element, false);
                });
                this.params.filters = setFilters;
            }
        }
    };
    /**
     * Resets the autocomplete container
     */
    Cludo.prototype.autocompleteRestore = function (clearRequestTimer) {
        if (clearRequestTimer === void 0) { clearRequestTimer = true; }
        if (this.clientTemplates) {
            this.autocompleteRestoreClient(clearRequestTimer);
        }
        else {
            this.autocompleteRestoreStandard(clearRequestTimer);
        }
    };
    /** Resets the autocomplete container -- clears the autocomplete_hint and
     *  search_autocomplete elements, and removes the related aria attributes from any elements  */
    Cludo.prototype.autocompleteRestoreStandard = function (clearRequestTimer) {
        var _this = this;
        if (clearRequestTimer === void 0) { clearRequestTimer = true; }
        if (this.debug === true) {
            return;
        }
        if (this.autocompleteDebounceTimerId && clearRequestTimer) {
            clearTimeout(this.autocompleteDebounceTimerId);
            this.autocompleteDebounceTimerId = null;
        }
        // remove autocomplete accessibility element and autocomplete container
        this.helpers.removeElement("autocomplete_hint");
        this.helpers.removeElement("search_autocomplete");
        // remove aria attributes that reference the just-removed elements
        this.helpers.removeAttributesWithSelector("aria-controls", "search_autocomplete");
        this.helpers.removeAttributesWithSelector("aria-describedby", "autocomplete_hint");
        this.selectedIndex = -1;
        this.searchComponentsKeys.forEach(function (key) {
            var _a, _b, _c, _d, _e, _f;
            (_b = (_a = _this.searchComponentsDictionary[key]) === null || _a === void 0 ? void 0 : _a.searchBoxInput) === null || _b === void 0 ? void 0 : _b.setAttribute("aria-expanded", "false");
            (_d = (_c = _this.searchComponentsDictionary[key]) === null || _c === void 0 ? void 0 : _c.searchBoxInput) === null || _d === void 0 ? void 0 : _d.removeAttribute("aria-activedescendant");
            (_f = (_e = _this.searchComponentsDictionary[key]) === null || _e === void 0 ? void 0 : _e.searchBoxInput) === null || _f === void 0 ? void 0 : _f.setAttribute("role", "combobox");
        });
    };
    // FACETS
    /**
     * Sets a new selected facet and optionally performs a search
     * @param {string} name Facet name
     * @param {string} value Selected facet value
     * @param {boolean} multivalues If true, adds/removes the passed facet from the active facets
     * @param {boolean} shouldSearch If true, runs a search after params are set
     */
    Cludo.prototype.facet = function (name, value, multivalues, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        if (value === null || value === "null") {
            this.params.facets[name] = [];
        }
        else {
            if (!this.applyMultiLevelFacets) {
                for (var key in this.facets) {
                    if (Object.prototype.hasOwnProperty.call(this.facets, key) && !multivalues) {
                        this.params.facets[key] = [];
                    }
                }
            }
            if (multivalues) {
                var index = this.params.facets[name].indexOf(value);
                if (index > -1) {
                    this.params.facets[name].splice(index, 1);
                }
                else {
                    this.params.facets[name].push(value);
                }
            }
            else {
                this.params.facets[name][0] = value;
            }
        }
        // Prep and execute search
        if (!shouldSearch) {
            return;
        }
        if (this.endlessScroll && this.jumpToTopOnFacetClick) {
            this.endlessScrollBackToTopClickEvent();
        }
        if (this.resetFiltersBeforeSearch) {
            this.params.filters = {};
        }
        this.searchEventTriggerQueue.push('facetsClick');
        this.page(1, this.jumpToTopOnFacetClick);
    };
    /**
     * Sets a new range type facet and optionally performs a search
     * @param {string} rangeType Set to 'range' for any number values or 'date' for date ranges
     * @param {string} field The field name to apply range facet to
     * @param {T extends string | number} from Lower bound of range
     * @param {T extends string | number} to Upper bound of range
     */
    Cludo.prototype.setRangeFacetMap = function (rangeType, field, from, to, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.params.facets[rangeType] = [field, from.toString(), to.toString()];
        // Prep and execute search
        if (!shouldSearch) {
            return;
        }
        if (this.endlessScroll && this.jumpToTopOnFacetClick) {
            this.endlessScrollBackToTopClickEvent();
        }
        if (this.resetFiltersBeforeSearch) {
            this.params.filters = {};
        }
        this.searchEventTriggerQueue.push('facetsClick');
        this.page(1, this.jumpToTopOnFacetClick);
    };
    Cludo.prototype.setDateRangeFacet = function (field, from, to, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        this.setRangeFacetMap('date', field, from, to, shouldSearch);
    };
    Cludo.prototype.setNumberRangeFacet = function (field, from, to, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        this.setRangeFacetMap('range', field, from, to, shouldSearch);
    };
    /** Clears a single facet value from the provided facet, then optionally searches
     * @param {string} facet Facet name
     * @param {string} value Facet value to remove
     * @param {boolean} shouldSearch If true, runs a search after params are set
     */
    Cludo.prototype.clearFacet = function (facet, value, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        var index = this.facets[facet].indexOf(value);
        if (index > -1) {
            this.facets[facet].splice(index, 1);
        }
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        if (this.jumpToTopOnFacetClick) {
            window.scrollTo(0, 0);
        }
        this.search();
    };
    /** Clears all facet values from a single facet, then optionally searches
     * @param {string} facetName Facet name
     * @param {boolean} shouldSearch If true, runs a search after params are set
     */
    Cludo.prototype.clearFacetByName = function (facetName, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.facets[facetName] = [];
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        if (this.jumpToTopOnFacetClick) {
            window.scrollTo(0, 0);
        }
        this.search();
    };
    /** Removes all facets */
    Cludo.prototype.clearAllFacets = function () {
        for (var key in this.facets) {
            this.facets[key] = [];
        }
    };
    /** Removes all facets and optionally performs a search */
    Cludo.prototype.clearAllFacetsAndSearch = function (shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.clearAllFacets();
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        if (this.jumpToTopOnFacetClick) {
            window.scrollTo(0, 0);
        }
        this.search();
    };
    // FILTERS
    Cludo.prototype.filter = function (name, value, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.params.filters[name] = value;
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        if (this.endlessScroll && this.jumpToTopOnFacetClick) {
            this.endlessScrollBackToTopClickEvent();
        }
        this.page(1, this.jumpToTopOnFacetClick);
    };
    Cludo.prototype.clearAllFilters = function (shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.params.filters = {};
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        if (this.jumpToTopOnFacetClick) {
            window.scrollTo(0, 0);
        }
        this.search();
    };
    // FACETS & FILTERS
    Cludo.prototype.clearAllFacetsAndFilters = function (shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        for (var key in this.facets) {
            this.facets[key] = [];
        }
        this.clearAllFilters(shouldSearch);
    };
    // SORTING
    Cludo.prototype.setSortOrder = function (name, value, shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.params.sort[name] = value;
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        this.page(1, false);
    };
    Cludo.prototype.clearSortOrder = function (shouldSearch) {
        if (shouldSearch === void 0) { shouldSearch = true; }
        // Set params
        this.clearSortParams();
        // Prep and execute search        
        if (!shouldSearch) {
            return;
        }
        this.search();
    };
    Cludo.prototype.clearSortParams = function () {
        this.params.sort = {};
    };
    // PAGING
    Cludo.prototype.page = function (pageNo, scrollToTop) {
        if (scrollToTop) {
            window.scrollTo(0, 0);
        }
        if (pageNo == "next") {
            this.params.page++;
        }
        else if (pageNo == "prev") {
            this.params.page--;
        }
        else {
            this.params.page = pageNo;
        }
        if (this.lastQuery) {
            this.params.query = this.lastQuery;
        }
        this.doSearch();
    };
    // DID YOU MEAN
    Cludo.prototype.setDidYouMean = function () {
        this.autocompleteRestore();
        this.params.query = this.didYouMean;
        this.search();
    };
    Cludo.prototype.setInputTypeAndSearch = function (inputType) {
        this.inputType = inputType;
        this.search();
    };
    /**
     * Search from autocomplete, after clearing facets / filters, or when a search is made with a fresh context.
     * This function will update the inputs to display the query, reset the page to 1, reset default facets,
     * and reset scroll if configured.
     */
    Cludo.prototype.search = function () {
        // hide keyboard on iOS
        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }
        for (var i = 0, len = this.searchInputsLength; i < len; i++) {
            var searchComponents = this.getSearchComponentsObject(this.searchComponentsKeys[i]);
            this.setElementValue(searchComponents.searchBoxInput, this.params.query);
        }
        this.params.page = 1;
        if (!this.helpers.isEmpty(this.facets)) {
            this.params.facets = this.facets;
        }
        this.autocompleteRestore();
        if (this.endlessScroll && this.jumpToTopOnFacetClick) {
            this.endlessScrollBackToTopClickEvent();
        }
        if (this.elemSearchResults.resultCount && !this.hideResultsCount) {
            this.elemSearchResults.resultCount.innerHTML = "";
        }
        if (this.resetSortBeforeSearch) {
            this.params.sort = this.initSortOrder;
        }
        this.doSearch();
    };
    // SEARCH
    Cludo.prototype.doSearch = function () {
        var _a, _b;
        this.updateQuerySessionId();
        if (!this.isSearchResultPage) {
            if (!this.queryIsNullOrEmpty() || this.allowSearchWithoutSearchword) {
                if (this.customCallbackBeforeRedirect) {
                    // pass the search request and search url to the callback in case anything should be modified
                    this.customCallbackBeforeRedirect(this.params, this.searchUrl);
                }
                this.redirectToUrl(this.searchUrl + "#?" + this.convertParamsToString());
            }
            return;
        }
        this.isLoadingResults = true;
        // clear the aria attributes referring to the error message from the inputs
        this.removeSearchInputAriaErrorAttributes();
        if (this.type === 'customOverlay') {
            this.helpers.addClass(this.resultsWrapper, this.ovarlayResultsWrapperOpenClass);
        }
        if (this.elemSearchResults.results) {
            if (this.endlessScroll) {
                this.isLazyLoading = true;
                this.helpers.addClass(this.endlessScrollElements.loadMore, "cludo-hidden");
                if (!this.clientTemplates) {
                    this.elemSearchResults.results.insertAdjacentHTML('beforeend', this.loadingHTML);
                }
            }
            else {
                if (!this.clientTemplates) {
                    this.elemSearchResults.results.innerHTML = this.loadingHTML;
                }
            }
        }
        if (this.elemSearchResults.didYouMean !== null) {
            this.didYouMean = this.elemSearchResults.didYouMean.innerHTML = '';
        }
        if (!this.queryIsNullOrEmpty() || this.allowSearchWithoutSearchword) {
            if (this.allowSearchWithoutSearchword) {
                this.params.query = this.params.query != "*" && this.params.query != "" ? this.params.query : "*";
            }
            if (this.changeWindowLocation === true) {
                LocationService.setHash("#?" + this.convertParamsToString());
            }
            var httpServiceUrl = this.searchApiUrl + "/" + this.customerId + "/" + this.engineId + "/" + "search";
            this.params.query = this.helpers.removeUnsafeCharacters(this.params.query);
            this.populateTraitsForRequest();
            if (this.customCallbackBeforeSearch) {
                // pass the search request to the callback in case anything should be modified
                this.customCallbackBeforeSearch(this.params);
            }
            this.updateRecentSearches(this.params.query);
            // Clear out the stored results so that the results component can react to it
            if (this.clientTemplates) {
                // For Evan -- do you have a better name for this function?
                this.clientTemplateBeforeSearch();
            }
            this.httpRequest("POST", httpServiceUrl, (this.clientTemplates) ? "searchResultTemplateClient" : "searchResultTemplate", this.elemSearchResults);
        }
        else {
            if (this.elemSearchResults.resultCount && !this.hideResultsCount) {
                this.elemSearchResults.resultCount.innerHTML = '';
            }
            if (this.elemSearchResults.filters && !this.clientTemplates) {
                for (var f = 0; this.elemSearchResults.filters.length > f; f++) {
                    this.elemSearchResults.filters[f].innerText = '';
                }
            }
            var noSearchErrorMsg = this.translateProvider.translate("no_search_term");
            this.errorTemplate(noSearchErrorMsg);
            // restore focus to the last modified search component
            if (this.lastModifiedSearchComponent !== null) {
                (_b = (_a = this.lastModifiedSearchComponent) === null || _a === void 0 ? void 0 : _a.searchBoxInput) === null || _b === void 0 ? void 0 : _b.focus();
            }
        }
    };
    // search for endless scroll (timeout added in order to make sure that results loads in the right order if param.page is higher than 1)
    /** Sequentially performs all previous searches for pages up to the current page (loading endless scroll) */
    Cludo.prototype.doSearchWithDelay = function (page, stopAtPage) {
        var _this = this;
        this.updateQuerySessionId();
        var delay = page === 1 ? 0 : 1000;
        if (page <= stopAtPage) {
            if (page > 1) {
                this.searchEventTriggerQueue.push('paginationNext');
            }
            if (!this.browserIsEdge14) {
                this.doSearchWithDelayTimer = window.setTimeout(function () {
                    _this.params.page = page;
                    _this.doSearch();
                    page++;
                    _this.doSearchWithDelay(page, stopAtPage);
                }, delay);
            }
            else {
                this.params.page = page;
                this.doSearch();
                page++;
                this.doSearchWithDelay(page, stopAtPage);
            }
        }
        else {
            this.doSearchWithDelayTimer = null;
        }
    };
    Cludo.prototype.updateQuerySessionId = function () {
        if (this.params.query != this.lastQuery) {
            this.querySessionId = this.generateUUID();
        }
        this.lastQuery = this.params.query;
    };
    // Check quicklinks for search word
    Cludo.prototype.hasQuicklink = function () {
        if (this.websiteSettings.quicklinks) {
            for (var i = 0, leni = this.websiteSettings.quicklinks.length; i < leni; i++) {
                for (var j = 0, lenj = this.websiteSettings.quicklinks[i].terms.length; j < lenj; j++) {
                    var matchQuery = undefined;
                    var fixedQuery = this._getFixedQuery();
                    var quicklink = this.websiteSettings.quicklinks[i];
                    if (this._isStringMatch(this.params.query, quicklink.terms[j].name)) {
                        matchQuery = this.params.query;
                    }
                    else if (this._isStringMatch(fixedQuery, quicklink.terms[j].name)) {
                        matchQuery = fixedQuery;
                        this.fixedQuery = undefined;
                    }
                    if (matchQuery) {
                        this.quicklink = quicklink;
                        this.quicklink.matchQuery = matchQuery;
                        return true;
                    }
                }
            }
        }
        return false;
    };
    Cludo.prototype.updateRecentSearches = function (query) {
        // Check the recentSearches array 
        // while the array has 5 items, remove the older items
        while (this.recentSearches.length > this.recentSearchLimit) {
            this.recentSearches.shift();
        }
        // Add the new items to the recentSearches array
        if (this.recentSearches.indexOf(query) == -1) {
            this.recentSearches.push(query);
        }
        // store the recentSearches on local storage
        this.storeRecentSearches();
    };
    // Redirect to page
    Cludo.prototype.redirectToUrl = function (redirectUrl) {
        LocationService.setHref(redirectUrl);
    };
    Cludo.prototype.getQueryParameterVariableName = function (paramName) {
        return this.paramsPrefix + paramName;
    };
    Cludo.prototype.getQueryFromUrl = function () {
        return this.helpers.stripHtmlTags(this.helpers.getURLParam(this.getQueryParameterVariableName('query'))
            .replace(/^[{]+|[}]+$/g, ''));
    };
    Cludo.prototype.getQueryFromState = function () {
        if (this.allowSearchWithoutSearchword && this.lastQuery === "") {
            return "*";
        }
        else {
            return this.lastQuery;
        }
    };
    Cludo.prototype.convertParamsToString = function () {
        var q = '';
        q += this.getQueryParameterVariableName("query") + "=" + encodeURIComponent(this.params.query);
        for (var facet in this.facets) {
            if (this.params.facets[facet].length) {
                var facetString = '';
                for (var i = 0; i < this.params.facets[facet].length; i++) {
                    if (i !== 0) {
                        facetString += this.urlListDelimiter;
                    }
                    facetString += encodeURIComponent(this.params.facets[facet][i]);
                }
                q += "&";
                q += this.getQueryParameterVariableName(facet) + "=" + facetString;
            }
        }
        for (var filter in this.filters) {
            if (typeof this.params.filters[filter] != "undefined" && this.params.filters[filter].length) {
                q += "&";
                q += this.getQueryParameterVariableName(filter) + "=" + this.params.filters[filter].toString();
            }
        }
        var sortKeys = Object.keys(this.params.sort);
        if (sortKeys[0] !== undefined) {
            q += "&";
            var sortString = '';
            for (var si = 0; si < sortKeys.length; si++) {
                if (si !== 0) {
                    sortString += this.urlListDelimiter;
                }
                sortString += encodeURIComponent(sortKeys[si] + '=' + this.params.sort[sortKeys[si]]);
            }
            q += this.getQueryParameterVariableName("sort") + "=" + sortString;
        }
        q += "&";
        q += this.getQueryParameterVariableName("page") + "=" + this.params.page;
        if (typeof this._getReferralPageTitle() !== 'undefined' && this._getReferralPageTitle() !== null && this._getReferralPageTitle() !== '') {
            q += "&" + this.getQueryParameterVariableName("refurl") + "=" + encodeURIComponent(this._getReferralUrl());
        }
        else if (!this.isSearchResultPage) {
            q += "&" + this.getQueryParameterVariableName("refurl") + "=" + encodeURIComponent(this._getCurrentUrl());
        }
        // If overlay search we are never on IsSearchResultPage and therefore need to add the params
        if (this.isOverlaySearch && (this._getReferralPageTitle() === '' || this._getReferralUrl() === '')) {
            q += "&" + this.getQueryParameterVariableName("refurl") + "=" + encodeURIComponent(this._getCurrentUrl()) + "&" + this.getQueryParameterVariableName("refpt") + "=" + encodeURIComponent(document.title);
        }
        // need to reuse the referral parameters otherwise we will just get it from the current page
        if (typeof this._getReferralUrl() !== 'undefined' && this._getReferralUrl() !== null && this._getReferralUrl() !== '') {
            q += "&" + this.getQueryParameterVariableName("refpt") + "=" + encodeURIComponent(this._getReferralPageTitle());
        }
        else if (!this.isSearchResultPage) {
            q += "&" + this.getQueryParameterVariableName("refpt") + "=" + encodeURIComponent(document.title);
        }
        // Add ac context info to the url if it exists
        if (this.pendingAcTitle) {
            q += "&" + this._getReferralAcTitleKey() + "=" + encodeURIComponent(this.pendingAcTitle);
            q += "&" + this._getReferralAcIndexKey() + "=" + encodeURIComponent(this.pendingAcIndex);
        }
        // Add input type info to the url if it exists
        if (this.inputType) {
            q += "&" + this.getQueryParameterVariableName("inputtype") + "=" + encodeURIComponent(this.inputType);
        }
        // When an engine is present, this enables it to persist.
        // TODO: This is done because when there are custom query parameters and they are wiped out, Internet Explorer reloads the page resulting in issues.
        //       At some point, we should upsert hash values or switch to the history object to avoid the page reloading when the query params change in IE.
        if (LocationService.getHash().indexOf(this.getQueryParameterVariableName("engine") + "=") > 0) {
            q += "&" + this.getQueryParameterVariableName("engine") + "=" + this.engineId;
        }
        return q;
    };
    // HTTP REQUESTS
    /** Performs a request to the provided url and runs the associated `template` callback method */
    Cludo.prototype.httpRequest = function (type, url, template, placeholder) {
        var _this = this;
        // For mulitpart/form use encoded string 
        var params = type === "POST" ? (this.xhrRequestHeader === "application/json" ? JSON.stringify(this.params) : "Params=" + encodeURIComponent(JSON.stringify(this.params))) : null;
        var requestOptions = {
            isIntranet: this.intranetSearch,
            authorizationKey: this.authorizationKey,
            contentType: this.xhrRequestHeader,
            customHeaders: this.customHttpHeaders
        };
        if (type === 'POST') {
            HttpService.post(url, params, requestOptions).then(function (data) { _this.httpCallback(data, template, placeholder, _this.params.query); }, function () { _this.httpFailureCallback(template); });
        }
        else {
            HttpService.get(url, requestOptions).then(function (data) { _this.httpCallback(data, template, placeholder, _this.params.query); }, function () { _this.httpFailureCallback(template); });
        }
    };
    /** LEGACY -- calls into httpSuccessCallback */
    Cludo.prototype.httpCallback = function (response, template, placeholder, originalQuery) {
        this.httpSuccessCallback(response, template, placeholder, originalQuery);
    };
    Cludo.prototype.httpSuccessCallback = function (response, template, placeholder, originalQuery) {
        var data = JSON.parse(response);
        data.query = originalQuery;
        this[template](data, placeholder);
        if (template === 'autocompleteTemplate') {
            this.autocompleteResponseData = data;
        }
    };
    Cludo.prototype.httpFailureCallback = function (template) {
        var errorTemplateMessage = this.translateProvider.translate("error");
        this.errorTemplate(errorTemplateMessage);
        if (template === 'autocompleteTemplate') {
            this.autocompleteResponseData = null;
        }
    };
    // HTML AUTOCOMPLETE TEMPLATE
    /** Injects autocomplete template adjacent to searchInputElement */
    Cludo.prototype.autocompleteTemplate = function (data, searchInputElement, suppressCallback) {
        // Sanity check
        if (!data) {
            return;
        }
        // Render autocomplete
        if (this.richAutocomplete) {
            this.richAutocompleteTemplate(data, searchInputElement);
        }
        else {
            this.standardAutocompleteTemplate(data, searchInputElement);
        }
        // Event handling and callbacks
        this.registerAutocompleteEvents();
        if (this.customCallbackAfterAutocomplete && !suppressCallback) {
            this.customCallbackAfterAutocomplete();
        }
    };
    /** Handle rendering of rich autocomplete */
    Cludo.prototype.richAutocompleteTemplate = function (data, searchInputElement) {
        var _this = this;
        // Check if this is not the most recent ac call we've made. Return if it is.
        if (data.query && this.params.query !== data.query) {
            return;
        }
        // Fix I18N tokens for ac
        if (this.translateSearchTemplates && data) {
            data.SearchResult = this.translateProvider.translateTokens(data.SearchResult);
        }
        this.selectedIndex = -1;
        this.elemAutocomplete.lists = [];
        this.elemAutocomplete.listsItems = [];
        if (!this.hideAutocomplete) {
            this.autocompleteRestore(false);
            if (data.TotalResults > 0 || data.TotalSuggestions > 0 || this.autocompleteForceUseTemplate === true) {
                var list = this.helpers.addElement(searchInputElement.parentNode, 'search_autocomplete', 'search_autocomplete');
                /* Create autocomplete hint element and append to search input */
                this.addAutocompleteHintToSearchInput(searchInputElement);
                this.elemAutocomplete.lists.push(list);
                list.innerHTML = data.SearchResult;
                var listItems = list.querySelectorAll('LI');
                listItems.forEach(function (listItem) {
                    var listItemInnerText = listItem.innerText;
                    var highlightedInnerText = _this.getAutocompleteHighlightedWords(listItemInnerText);
                    var richAutocompleteLink = listItem.getElementsByTagName("a")[0];
                    if (richAutocompleteLink) {
                        richAutocompleteLink.innerHTML = highlightedInnerText;
                    }
                    else {
                        listItem.innerHTML = highlightedInnerText;
                    }
                });
                this.elemAutocomplete.listsItems = Array.from(listItems);
            }
        }
    };
    /** Handle rendering of standard autocomplete */
    Cludo.prototype.standardAutocompleteTemplate = function (data, searchInputElement) {
        var _a;
        this.selectedIndex = -1;
        this.elemAutocomplete.lists = [];
        this.elemAutocomplete.listsItems = [];
        // Clear out old autocomplete results
        this.autocompleteRestore(false);
        // Derive suggestions from the response data
        var suggestions = ((_a = data === null || data === void 0 ? void 0 : data.Suggestions) === null || _a === void 0 ? void 0 : _a.map(function (suggestion) { var _a, _b; return (_b = (_a = suggestion === null || suggestion === void 0 ? void 0 : suggestion.Fields) === null || _a === void 0 ? void 0 : _a.Title) === null || _b === void 0 ? void 0 : _b.Value; })) || [];
        // If there aren't suggestions, or we don't currently have a query in the input, don't create autocomplete elements
        if (!suggestions.length || this.hideAutocomplete || !this.params.query) {
            return;
        }
        /* Create autocomplete hint element */
        this.addAutocompleteHintToSearchInput(searchInputElement);
        var list = document.createElement("UL");
        list.className = "search_autocomplete";
        list.setAttribute("id", "search_autocomplete");
        list.setAttribute("role", "listbox");
        list.setAttribute("aria-describedby", "autocomplete_hint");
        this.elemAutocomplete.lists.push(list);
        this.populateAutocompleteList(suggestions, list);
        /* Appends the Autocomplete hint element to the search input or the first ancestor that doesn't have a shadow root */
        var parentNode = this.helpers.findNonShadowAncestor(searchInputElement.parentElement);
        parentNode.appendChild(list);
    };
    Cludo.prototype.populateAutocompleteList = function (data, listElement) {
        for (var i = 0, len = data.length; i < len; i++) {
            var listItem = document.createElement("li");
            listItem.innerHTML = this.getAutocompleteHighlightedWords(data[i]).replace("!", "");
            listItem.setAttribute("role", "option");
            listItem.setAttribute("aria-label", data[i]);
            listItem.setAttribute("aria-posinset", i.toString());
            listItem.setAttribute("aria-setsize", len.toString());
            //Add an id to support aria-activedescendant
            listItem.setAttribute("id", "cludo-list-item-" + i);
            listElement.appendChild(listItem);
            this.elemAutocomplete.listsItems.push(listItem);
        }
    };
    Cludo.prototype.registerAutocompleteEvents = function () {
        var listLen = this.elemAutocomplete.lists.length;
        for (var i = 0, len = listLen; i < len; i++) {
            this.elemAutocomplete.lists[i].addEventListener('mouseover', this.autocompleteMouseOverEvent, true);
        }
        var listItemsLen = this.elemAutocomplete.listsItems.length;
        for (var i = 0, len = listItemsLen; i < len; i++) {
            this.elemAutocomplete.listsItems[i].addEventListener('mousedown', this.autocompleteMouseDownEvent, true);
        }
    };
    Cludo.prototype.getAutocompleteHighlightedWords = function (listItem) {
        var queryItems = this.params.query.split(" ");
        for (var j = 0, lenQ = queryItems.length; j < lenQ; j++) {
            if (typeof queryItems[j] !== 'undefined' && queryItems[j] !== '') {
                listItem = this.helpers.highlightSearchword(listItem, queryItems[j]);
            }
        }
        return listItem;
    };
    Cludo.prototype.createAutocompleteHintElement = function () {
        if (!this.srOnlyStylesInjected) {
            var css = "\n                .cludo-sr-only {\n                    position: absolute;\n                    width: 1px;\n                    height: 1px;\n                    padding: 0;\n                    overflow: hidden;\n                    clip: rect(0, 0, 0, 0);\n                    border: 0;\n                }\n            ";
            this.helpers.addCssStyles(css);
            this.srOnlyStylesInjected = true;
        }
        var autocompleteHintEl = document.createElement("span");
        autocompleteHintEl.id = "autocomplete_hint";
        /* add accessibility class for mac screen readers */
        autocompleteHintEl.className = "cludo-sr-only";
        autocompleteHintEl.innerText = this.translateProvider.translateTokens("{{template_autocomplete_hint}}");
        /* add accessibility attributes*/
        autocompleteHintEl.setAttribute("aria-hidden", "false");
        autocompleteHintEl.setAttribute("aria-atomic", "true");
        autocompleteHintEl.setAttribute("role", "status");
        autocompleteHintEl.setAttribute("aria-live", "polite");
        return autocompleteHintEl;
    };
    /* Create autocomplete hint element, append to search input, add aria attributes */
    Cludo.prototype.addAutocompleteHintToSearchInput = function (searchInputElement) {
        var autocompleteHintEl = this.createAutocompleteHintElement();
        this.helpers.findNonShadowAncestor(searchInputElement.parentElement).appendChild(autocompleteHintEl);
        /* accessibility attributes search input */
        searchInputElement.setAttribute("role", "combobox");
        searchInputElement.setAttribute("aria-describedby", "autocomplete_hint");
        searchInputElement.setAttribute("aria-autocomplete", "list");
        // Set the aria-controls with the list id
        searchInputElement.setAttribute("aria-controls", "search_autocomplete");
        searchInputElement.setAttribute("aria-expanded", "true");
    };
    // AUTOCOMPLETE EVENT HANDLERS
    Cludo.prototype.autocompleteMouseOverEvent = function (e) {
        var target = e.currentTarget;
        if (e && e.stopPropagation) {
            e.stopPropagation();
        }
        else {
            e.cancelBubble = true;
        }
        if (!(target instanceof HTMLElement)) {
            return;
        }
        var listItems = target.querySelectorAll('LI');
        var len = listItems.length;
        for (var i = 0; i < len; i++) {
            this.helpers.removeClass(listItems[i], "active");
        }
        this.selectedIndex = -1;
    };
    Cludo.prototype.autocompleteMouseDownEvent = function (e) {
        var target = e.currentTarget;
        if (e && e.stopPropagation) {
            e.stopPropagation();
        }
        else {
            e.cancelBubble = true;
        }
        if (!(target instanceof HTMLElement)) {
            return;
        }
        this.params.query = this.helpers.stripSpecialChars(target.innerText);
        for (var i = 0, len = this.searchInputsLength; i < len; i++) {
            var searchComponents = this.getSearchComponentsObject(this.searchComponentsKeys[i]);
            this.setElementValue(searchComponents.searchBoxInput, this.params.query);
        }
        this.autocompleteSetSelectedItem(target);
    };
    Cludo.prototype.autocompleteKeyDownEvent = function (keynum, target, e) {
        var numberAutocompleteListItems = this.elemAutocomplete.listsItems.length;
        var searchComponents = this.getSearchComponentsObjectFromSearchInputElement(target);
        if (e && e.preventDefault) {
            e.preventDefault();
        }
        else {
            e.returnValue = false;
        }
        var selectedNode;
        if (keynum === this.helpers.ENTER) {
            if (this.selectedIndex < 0) {
                // no suggestion was selected in autocomplete, user is just typing search word and clicking enter in the search box
                this.hideAutocomplete = true;
                this.autocompleteRestore();
                if (e && e.preventDefault) {
                    e.preventDefault();
                }
                else {
                    e.returnValue = false;
                }
                this.params.query = this.helpers.stripHtmlTags(target.value);
                if (this._handleQuickLinks()) {
                    return;
                }
                this.setFacetsBeforeSearch(searchComponents.searchBoxFacets);
                if (this.isOverlaySearch) {
                    this.overlayOpenModalWithSearch();
                }
                if (this.resetFiltersBeforeSearch) {
                    this.params.filters = {};
                }
                this.setInputTypeAndSearch(this.inputTypeStandardKey);
            }
            else {
                selectedNode = this.elemAutocomplete.listsItems[this.selectedIndex];
                this.params.query = this.helpers.stripSpecialChars(this.helpers.stripHtmlTags(selectedNode.innerText));
                this.autocompleteSetSelectedItem(selectedNode);
            }
        }
        else if (!this.disableAutocomplete && (keynum === this.helpers.DOWN || keynum === this.helpers.UP) && numberAutocompleteListItems > 0) {
            if (keynum === this.helpers.DOWN) {
                this.selectedIndex = (this.selectedIndex == numberAutocompleteListItems - 1) ? -1 : this.selectedIndex;
                this.selectedIndex++;
            }
            if (keynum === this.helpers.UP) {
                this.selectedIndex = (this.selectedIndex == 0 || this.selectedIndex == -1) ? numberAutocompleteListItems : this.selectedIndex;
                this.selectedIndex--;
            }
            this.autocompleteSetActiveItem(this.selectedIndex, target);
        }
    };
    /** Removes the "active" attributes from all suggestions, then sets them on the currently selected suggestion */
    Cludo.prototype.autocompleteSetActiveItem = function (selectedIndex, searchInput) {
        var _this = this;
        // Clear out old classnames/attributes
        this.elemAutocomplete.listsItems.forEach(function (item) {
            _this.helpers.removeClass(item, "active");
            item.ariaSelected = "false";
        });
        // Set "active" attributes on the currently selected suggestion/result
        var selectedNode = this.elemAutocomplete.listsItems[selectedIndex];
        selectedNode.className = "active";
        selectedNode.ariaSelected = "true";
        // Get sanitized item text
        var itemText = this.helpers.trim(selectedNode.innerText);
        // Temp fix for PH Metropol until characters are replaced in the backend
        var sanitizedItemText = itemText.replace(/(\&shy;|­|&#173;)/gi, "");
        // Update inputs with the selected item text
        this.params.query = this.helpers.stripSpecialChars(sanitizedItemText);
        for (var i = 0; i < this.searchInputsLength; i++) {
            var searchComponentsObject = this.getSearchComponentsObject(this.searchComponentsKeys[i]);
            this.setElementValue(searchComponentsObject.searchBoxInput, this.params.query);
        }
        // Set aria-activedescendant on the search input when an item is selected
        searchInput.setAttribute("aria-activedescendant", selectedNode.id);
    };
    Cludo.prototype.autocompleteSetSelectedItem = function (target) {
        var _this = this;
        var _a;
        if (target.hasChildNodes()) {
            if (target.getElementsByTagName("a")[0]) {
                var richAutocompleteLink_1 = target.getElementsByTagName("a")[0].href;
                this.trackClickEventHandlerForRichAutocompleteLink(target.getElementsByTagName("a")[0]);
                this.pushClickLog(this._buildClickLogObjectForRichAutocompleteLink(), function () {
                    _this.redirectToUrl(richAutocompleteLink_1);
                });
                return;
            }
            else {
                if (this._handleQuickLinks()) {
                    return;
                }
                var autocompleteParent = this.helpers.closest(target, "#search_autocomplete");
                if (autocompleteParent && typeof ((_a = autocompleteParent.parentElement) === null || _a === void 0 ? void 0 : _a.id) !== 'undefined') {
                    this.setFacetsBeforeSearch(this.getSearchComponentsObjectFromAutocompleteElement(autocompleteParent).searchBoxFacets);
                }
                if (this.isOverlaySearch) {
                    this.overlayOpenModalWithSearch();
                }
                if (this.resetFiltersBeforeSearch) {
                    this.params.filters = {};
                }
                // Set pending ac values. For index, we add one to make it 1-based.
                this.pendingAcTitle = this.lastAcQuery;
                this.pendingAcIndex = [].indexOf.call(target.parentNode.children, target) + 1;
                this.setInputTypeAndSearch(this.inputTypeStandardKey);
            }
        }
    };
    // HTML SEARCH RESULTS TEMPLATE
    // Injects search results template to placeholder
    Cludo.prototype.searchResultTemplate = function (data, placeholder) {
        var _this = this;
        this.isLoadingResults = false;
        if (this.publicSettingsRetrieved === false) {
            // call itself in 250 ms to make sure we have public settings
            this.reCallSearchResultTemplateTimer = window.setTimeout(function () {
                _this.searchResultTemplate(data, placeholder);
            }, 250);
        }
        else {
            // Fix I18N tokens for search results and facets
            if (this.translateSearchTemplates && data) {
                data.Facets = this.translateProvider.translateTokens(data.Facets);
                data.SearchResult = this.translateProvider.translateTokens(data.SearchResult);
            }
            this.totalDocuments = data.TotalDocuments;
            this.fixedQuery = data.FixedQuery;
            this.banners = data.Banners;
            this.responseTime = data.ResponseTime;
            this.queryId = data.QueryId;
            this.track();
            if (this.endlessScroll) {
                this.isLazyLoading = false;
                this.helpers.removeElement('cludo-loading');
                if (this.params.page == 1) {
                    placeholder.results.innerHTML = data.SearchResult;
                    // Check if window is taller than document and, if so, expose load more button
                    if (!this.helpers.pageCanScroll(this.endlessScroll.bottomOffset) &&
                        !(this.params.page === Math.ceil(this.totalDocuments / this.endlessScroll.resultsPerPage)) && this.totalDocuments > 0) {
                        this.helpers.removeClass(this.endlessScrollElements.loadMore, 'cludo-hidden');
                    }
                }
                else {
                    placeholder.results.insertAdjacentHTML('beforeend', data.SearchResult);
                    if (this.userIsUsingTabulator) {
                        // in order to prevent LI item focus when loading many pages on page load - focus back on current element
                        placeholder.results.getElementsByTagName("ul")[this.params.page - 1].children[0].getElementsByTagName("a")[0].focus();
                    }
                }
                if (this.params.page >= this.endlessScroll.stopAfterPage && this.totalDocuments > 0) {
                    if (this.params.page === Math.ceil(this.totalDocuments / this.endlessScroll.resultsPerPage)) {
                        this.helpers.addClass(this.endlessScrollElements.loadMore, 'cludo-hidden');
                    }
                    else {
                        this.helpers.removeClass(this.endlessScrollElements.loadMore, 'cludo-hidden');
                    }
                }
            }
            else {
                placeholder.results.innerHTML = data.SearchResult;
            }
            // Detect link fragments from template response
            if (placeholder.results.querySelector('span.cludo-highlight-fragment')) {
                this.parseAndAddLinkFragments(placeholder);
            }
            if (this.isOverlaySearch && this.type !== 'customOverlay') {
                this.elemOverlaySearch.searchBoxContent.style.zIndex = "1";
            }
            if (placeholder.filters !== null) {
                for (var i = 0, len = placeholder.filters.length; i < len; i++) {
                    placeholder.filters[i].innerHTML = data.TotalDocuments > 0 || !this.hideSearchFiltersIfNoResult ? data.Facets : '';
                }
            }
            if (data.DidYouMean != "" && placeholder.didYouMean !== null && typeof placeholder.didYouMean !== 'undefined' && data.TotalDocuments < 10) {
                placeholder.didYouMean.innerHTML = this.translateProvider.translate("did_you_mean", data.DidYouMean);
                this.didYouMean = data.DidYouMean;
            }
            // Render banners outside of the template (if banner isn't in search template)
            this.renderOutsideBanners(data, placeholder);
            if (placeholder.resultCount !== null) {
                placeholder.resultCount.innerHTML = this.getResultCountHtml({ fixedQuery: data.FixedQuery, totalDocuments: data.TotalDocuments });
            }
            if (placeholder.relatedSearches && data && data.RelatedSearchesResult) {
                var translatedRelatedSearchesResult = this.translateProvider.translateTokens(data.RelatedSearchesResult);
                for (var i = 0; i < placeholder.relatedSearches.length; i++) {
                    placeholder.relatedSearches[i].innerHTML = '';
                    placeholder.relatedSearches[i].innerHTML += translatedRelatedSearchesResult;
                }
            }
            else if (placeholder.relatedSearches && data && !data.RelatedSearchesResult) {
                for (var i = 0; i < placeholder.relatedSearches.length; i++) {
                    placeholder.relatedSearches[i].innerHTML = '';
                }
            }
            if (this.focusOnResultsAfterSearch && (!this.endlessScroll || this.params.page == 1)) {
                this.focusOnResults();
            }
            this.isSearchAfterRedirect = false;
            if (this.customCallbackAfterSearch) {
                this.customCallbackAfterSearch(data);
            }
            this.searchResultsEvents();
            if (!this.pageInitFromBackForward) {
                this._handleQuickLinks();
            }
            // Some clients may use the button with one class as others use a div with a different class
            var mobileBtn = this.helpers.querySelector('.search-filters .search-filters-mobile-button');
            var mobileBtnDiv = this.helpers.querySelector('.search-filters .search-filter-header-mobile');
            var mobileNav = void 0;
            // so here we wanna make sure to cover both options 
            if (mobileBtn) {
                mobileNav = mobileBtn;
            }
            else if (mobileBtnDiv) {
                mobileNav = mobileBtnDiv;
            }
            // check that we have a mobile navigation system in place: either div or button
            // and add the accessibility attr needed
            if (mobileNav) {
                mobileNav.setAttribute('aria-label', this.translateProvider.translate("toggle_filters_label"));
                mobileNav.setAttribute('aria-expanded', 'false');
                mobileNav.setAttribute('aria-controls', 'facet-list');
                mobileNav.setAttribute('role', 'button');
                mobileNav.setAttribute('tabindex', '0');
            }
            var searchFilterList = this.helpers.querySelector('.search-filters ul');
            if (searchFilterList && !searchFilterList.getAttribute('id')) {
                this.helpers.querySelector('.search-filters ul').setAttribute('id', 'facet-list');
            }
        }
    };
    /**
     * Given data from a search response, gets a translated and escaped results summary string
     * @param data Object that contains fixedQuery and totalDocuments properties (properties
     *              extracted so that it's not hard-coupled to either the SearchResponse or
     *              ClientSearchResponse interfaces)
     * @returns A "results summary" string, with HTML tags escaped, and translated using tokenized strings
     */
    Cludo.prototype.getResultCountHtml = function (data) {
        var _this = this;
        var resultCountHTML = "";
        if (this.useFixedQueryInResultsCount && data.fixedQuery) {
            resultCountHTML = this.translateProvider.translate("your_search_on", this.helpers.stripHtmlTags(this.params.query)) + this.translateProvider.translate("total_results", "0");
            resultCountHTML += this.translateProvider.translateWithParameters("searched_instead", { 'number': data.totalDocuments.toString(), 'term': data.fixedQuery });
        }
        else {
            if (0 === data.totalDocuments && null !== this.customNoResultsMessage) {
                resultCountHTML = this.customNoResultsMessage;
            }
            else {
                var totalResultsText = data.totalDocuments === 1 ? this.translateProvider.translate("total_result", data.totalDocuments.toString()) : this.translateProvider.translate("total_results", data.totalDocuments.toString());
                resultCountHTML = this.translateProvider.translate("your_search_on", this.helpers.stripHtmlTags(this.params.query)) + totalResultsText;
                resultCountHTML += Object.keys(this.facets).map(function (key) {
                    return _this.facets[key];
                }).filter(function (x) {
                    return x && x.length > 0;
                }).map(function (item) {
                    return _this.translateProvider.translate("in_category", item.toString());
                }).join(", ").replace(/, ([^,]*)$/, this.translateProvider.translate("and") + " $1");
            }
        }
        return resultCountHTML;
    };
    Cludo.prototype.errorTemplate = function (msg) {
        if (this.clientTemplates) {
            this.errorTemplateClient(msg);
            return;
        }
        if (this.resultsWrapper != null) {
            this.elemSearchResults.results.innerHTML = msg;
            var noSearchTermElem = this.resultsWrapper.querySelector('.cludo-no-search-term');
            if (noSearchTermElem != null) {
                noSearchTermElem.setAttribute('id', NO_SEARCH_TERM_ELEM_ID);
                var searchComponents = this.getSearchComponentsArray();
                searchComponents.forEach(function (searchComponent) {
                    var searchInputElem = searchComponent.searchBoxInput;
                    if (searchInputElem != null) {
                        searchInputElem.setAttribute('aria-invalid', 'true');
                        searchInputElem.setAttribute('aria-errormessage', NO_SEARCH_TERM_ELEM_ID);
                    }
                });
            }
        }
        if (this.elemSearchResults.relatedSearches && this.elemSearchResults.relatedSearches.length > 0) {
            for (var i = 0; i < this.elemSearchResults.relatedSearches.length; i++) {
                this.elemSearchResults.relatedSearches[i].innerHTML = '';
            }
        }
    };
    /**
     * remove aria-invalid attribute and aria-errormessage attribute from each of the registered search inputs
     */
    Cludo.prototype.removeSearchInputAriaErrorAttributes = function () {
        var searchComponents = this.getSearchComponentsArray();
        searchComponents.forEach(function (searchComponent) {
            var searchInputElem = searchComponent.searchBoxInput;
            if (searchInputElem != null) {
                searchInputElem.removeAttribute('aria-invalid');
                searchInputElem.removeAttribute('aria-errormessage');
            }
        });
    };
    /** Add `data-cludo` attributes and click/keyup event listeners to the passed anchor tag */
    Cludo.prototype.addAnchorAttributesAndListeners = function (anchor) {
        var _this = this;
        var href = anchor.href;
        if (anchor.getAttribute("data-page")) {
            return;
        }
        if (href && href.length > 0) {
            if (this.helpers.closest(anchor, "[data-cludo-result=banner]")) {
                var bannerLinkTitle = anchor.getAttribute("title") !== null ? anchor.getAttribute("title")
                    : anchor.innerText !== '' ? anchor.innerText
                        : this.helpers.closest(anchor, "[data-cludo-result=banner]").getAttribute("data-cludo-title");
                var bannerId = this.helpers.closest(anchor, "[data-cludo-result=banner]").getAttribute("data-cludo-id");
                anchor.setAttribute("data-cludo-result", "banner");
                anchor.setAttribute("data-cludo-index", "1");
                anchor.setAttribute("data-cludo-object-id", bannerId);
                anchor.setAttribute("data-cludo-title", bannerLinkTitle);
                if (decodeURIComponent(href).indexOf('#?' + this.paramsPrefix) !== -1) {
                    anchor.addEventListener("click", function (e) {
                        e.preventDefault();
                        _this.linkToSearchClickEvent(anchor);
                    });
                }
            }
            var pageNo = this.helpers.getURLParam(this.getQueryParameterVariableName("page"));
            anchor.setAttribute("data-cludo-page", pageNo);
            anchor.addEventListener("click", this.searchResultTrackClickEventHandler, true);
            anchor.addEventListener("keyup", this.searchResultKeyUpEvent, true);
        }
    };
    /** Renders the banners in the proper container if they aren't included in the search template */
    Cludo.prototype.renderOutsideBanners = function (data, placeholder) {
        if (!this.bannerIsInSearchTemplate && placeholder.banner !== null) {
            if (data.Banners.length) {
                var bannerHtml = "";
                for (var i = 0, len = data.Banners.length; i < len; i++) {
                    bannerHtml += '<div data-cludo-banner-location="outside" data-cludo-result="banner" data-cludo-id="' + data.Banners[i].Id + '" data-cludo-title="' + data.Banners[i].Name + '" class="cludo-banner" role="banner">' + data.Banners[i].Banner + '</div>';
                }
                placeholder.banner.innerHTML = bannerHtml;
            }
            else {
                placeholder.banner.innerHTML = "";
            }
        }
    };
    Cludo.prototype.settingsTemplate = function (data, searchInputElement) {
        this.websiteSettings = {
            Engines: data.Engines,
            customEngineSettings: data.customEngineSettings,
            enableAnonymousTracking: data.enableAnonymousTracking,
            enableGoogleAnalyticsIntegration: data.enableGoogleAnalyticsIntegration,
            enableGoogleTagManagerIntegration: data.enableGoogleTagManagerIntegration,
            enableSiteimproveAnalyticsIntegration: data.enableSiteimproveAnalyticsIntegration,
            optOutCookieTracking: data.optOutCookieTracking,
            quicklinks: data.quicklinks,
            subscriptionDigest: data.subscriptionDigest,
            instantSuggestionsConfiguration: data.instantSuggestionsConfiguration ? JSON.parse(data.instantSuggestionsConfiguration) : undefined,
            configurations: (data.configurations) ? data.configurations : {}
        };
        this.configureFeaturesFromPublicSettings(this.websiteSettings, searchInputElement);
    };
    Cludo.prototype.configureFeaturesFromPublicSettings = function (settings, searchInputElement) {
        this.publicSettingsRetrieved = true;
        // Enable/disable features
        if (settings.subscriptionDigest && settings.subscriptionDigest.features) {
            this.enabledFeatures = settings.subscriptionDigest.features;
            this.toggleSettingsForEnabledFeatures();
        }
        // Hack for Siteimprove users if they are using links with /hash/?cludoquery=
        if (settings.enableSiteimproveAnalyticsIntegration === true && /\/hash\/\?cludoquery=/i.test(LocationService.getHref())) {
            LocationService.setHref(LocationService.getHref().replace(/\/hash\/\?cludoquery=/i, '#?cludoquery='));
        }
        // Configure instant suggestions
        if (settings.instantSuggestionsConfiguration) {
            this.showRecentSearches = (settings.instantSuggestionsConfiguration.showRecentSearches === true);
        }
        // If customer opts out of tracking, use NoOp storage	
        if (settings.optOutCookieTracking) {
            this.storageService.disableTrackingForCustomer();
        }
        // Check if the user has access to InstantSuggestion feature
        if (this.showInstantSuggestions) {
            this.setInstantSuggestions(searchInputElement);
        }
        // Initialize analytics integrations communicator
        this.analyticsIntegrationCommunicator = AnalyticsIntegrationFactory.getIntegrationsCommunicator(this);
    };
    Cludo.prototype.setInstantSuggestions = function (searchInputElement) {
        var _this = this;
        var instantSuggestions = [];
        var limit;
        var instantSuggestionsData;
        var recentSearchesData;
        var suggestedHeader = this.suggestedSearchesHeader || this.translateProvider.translate("suggested_searches_title");
        var recentHeader = this.recentSearchesHeader || this.translateProvider.translate("recent_searches_title");
        if (this.websiteSettings.instantSuggestionsConfiguration) {
            instantSuggestions = this.websiteSettings.instantSuggestionsConfiguration.suggestions ? this.websiteSettings.instantSuggestionsConfiguration.suggestions : [];
            if (this.websiteSettings.instantSuggestionsConfiguration.limit != null && this.websiteSettings.instantSuggestionsConfiguration.limit != undefined) {
                limit = this.websiteSettings.instantSuggestionsConfiguration.limit;
            }
        }
        if (instantSuggestions.length) {
            // Pare down the suggestions to the limit
            if (limit && instantSuggestions.length > limit) {
                instantSuggestions = instantSuggestions.slice(limit);
            }
            // Set the data
            instantSuggestionsData = { label: suggestedHeader, items: instantSuggestions };
        }
        // Check if there are recent searches,
        // and if the user wants to display them
        if (this.showRecentSearches) {
            this.recentSearches = this.getRecentSearchesFromStorage();
            // Verify if the localStorage has more than 1 value in the array 
            // Because we filter out the recent search
            if (this.recentSearches.length > 1) {
                recentSearchesData = {
                    label: recentHeader,
                    items: this.recentSearches.filter((function (v) {
                        return v.toLowerCase() !== _this.params.query.toLowerCase();
                    })).reverse()
                };
            }
        }
        if (!searchInputElement && !this.headlessSearch) {
            return;
        }
        if (this.clientTemplates) {
            this.setInstantSuggestionsClient(instantSuggestionsData, recentSearchesData);
        }
        else {
            this.clearAutocompleteBeforeSettingsTemplate();
            this.suggestionsBoxTemplate([instantSuggestionsData, recentSearchesData], searchInputElement, "instant_suggestions");
            this.registerAutocompleteEvents();
        }
    };
    Cludo.prototype.suggestionsBoxTemplate = function (data, searchInputElement, className) {
        var _this = this;
        var autocompleteHintEl = document.createElement("span");
        autocompleteHintEl.id = "autocomplete_hint";
        autocompleteHintEl.style.display = "none";
        autocompleteHintEl.innerText = this.translateProvider.translateTokens("{{template_autocomplete_hint}}");
        searchInputElement.setAttribute("aria-describedby", "autocomplete_hint");
        searchInputElement.setAttribute("aria-controls", "search_autocomplete");
        searchInputElement.setAttribute("aria-expanded", "true");
        var container = document.createElement("div");
        container.className = "search_autocomplete " + className;
        container.setAttribute("id", "search_autocomplete");
        data.forEach(function (element) {
            if (element) {
                _this.suggestionsBoxTemplateInner(container, element.items, element.label);
            }
        });
        var parentElement = this.helpers.findNonShadowAncestor(searchInputElement.parentElement);
        parentElement.appendChild(autocompleteHintEl);
        parentElement.appendChild(container);
    };
    Cludo.prototype.suggestionsBoxTemplateInner = function (container, data, label) {
        var header = document.createElement("h3");
        header.innerText = label;
        var list = document.createElement("UL");
        list.setAttribute("role", "listbox");
        this.elemAutocomplete.lists.push(list);
        this.populateAutocompleteList(data, list);
        container.appendChild(header);
        container.appendChild(list);
    };
    Cludo.prototype.clearAutocompleteBeforeSettingsTemplate = function () {
        this.elemAutocomplete.lists = [];
        this.elemAutocomplete.listsItems = [];
        this.autocompleteRestore();
    };
    /**
     * Adds event handling for clicking description fragment (span) elements. \
     * Assumes each search result is wrappen in an anchor tag, and that descriptions are separated by span tags
     * @param {HTMLElement} placeholder Reference to the results wrapper
     */
    Cludo.prototype.parseAndAddLinkFragments = function (placeholder) {
        var _this = this;
        var resultsElem = placeholder.results;
        var resultAnchors = resultsElem.querySelectorAll('[data-cludo-result="searchresult"]');
        var _loop_6 = function (i) {
            var result = resultAnchors[i];
            if (result.href.indexOf('#:~:text=') !== -1) {
                return "continue";
            }
            var fragmentSpans = result.querySelectorAll('span.cludo-highlight-fragment');
            var _loop_7 = function (j) {
                // attach click handlers to each span that records the description
                var span = fragmentSpans[j];
                span.setAttribute('tabindex', '0');
                span.setAttribute('role', 'link');
                span.addEventListener('click', function () {
                    _this.linkFragment = encodeURIComponent(span.innerText);
                });
                span.addEventListener('keydown', function (e) {
                    if (e.code === "Space" || e.code === "Enter") {
                        _this.linkFragment = encodeURIComponent(span.innerText);
                        _this.searchResultTrackClickEventHandler(e, result);
                    }
                });
            };
            for (var j = 0; j < fragmentSpans.length; j++) {
                _loop_7(j);
            }
            // set the anchor tag href to the first fragment
            if (fragmentSpans && fragmentSpans.length && result.href.indexOf('#:~:text=') === -1) {
                var firstFragmentSpan = fragmentSpans[0];
                var firstDescription = encodeURIComponent(firstFragmentSpan.innerText);
                var fragmentString = '#:~:text=' + firstDescription;
                result.href += fragmentString;
            }
        };
        for (var i = 0; i < resultAnchors.length; i++) {
            _loop_6(i);
        }
    };
    Cludo.prototype.focusOnResults = function () {
        if (this.totalDocuments && !this.isSearchAfterRedirect) {
            var result = this.elemSearchResults.results.querySelectorAll('a')[0];
            if (this.didYouMean !== '' && this.elemSearchResults.didYouMean !== null) {
                result = this.elemSearchResults.didYouMean.querySelectorAll('a')[0];
            }
            if (result) {
                result.setAttribute('contenteditable', 'true');
                result.focus();
                result.removeAttribute('contenteditable');
            }
        }
    };
    // OVERLAY
    Cludo.prototype.isSearchWithOverlay = function () {
        if (this.type === 'standardOverlay' || this.type === 'standardOverlayWithDynamicSearchBox' || this.type === 'customOverlay') {
            return true;
        }
        return false;
    };
    Cludo.prototype.overlaySetTopSearchBox = function () {
        this.elemOverlaySearch.searchBox = this.helpers.addElement(document.body, '', 'cludo-search-form');
        this.elemOverlaySearch.searchBox.style.position = 'absolute';
        this.elemOverlaySearch.searchBox.style[this.searchBoxPosition.align] = this.searchBoxPosition.x + 'px';
        this.elemOverlaySearch.searchBox.style.top = this.searchBoxPosition.y + 'px';
        this.elemOverlaySearch.searchBoxLabel = this.helpers.addLabelElement(this.elemOverlaySearch.searchBox, 'cludo-search-form-input', this.translateProvider.translate('search_input_label'));
        this.elemOverlaySearch.searchBoxInput = this.helpers.addInputElement(this.elemOverlaySearch.searchBox, 'searchrequest', 'search-input', this.initSearchBoxText, 'cludo-search-form-input', this.autocompleteParamDefaultValue);
        this.elemOverlaySearch.searchBoxButton = this.helpers.addButtonElement(this.elemOverlaySearch.searchBox, 'search-button', 'search-button', this.translateProvider.translate('search_button_text'));
    };
    Cludo.prototype.overlayOpenModalWithSearch = function () {
        var _this = this;
        this.isSearchResultPage = true;
        if (this.type !== 'customOverlay') {
            if (this.elemOverlaySearch.overlay === null) {
                this.setOverlayElements();
                this.setResultElements();
                this.overlayAddEventsToSearchElements();
            }
            //add & remove css classes to overlay items, set theme color
            document.body.className = document.body.className + ' cludo-search-modal-active';
            this.helpers.removeClass(this.elemOverlaySearch.overlay, 'cludo-search-modal-overlay-inactive');
            //input box in overlay - set value & focus
            if (this.elemOverlaySearch.searchBoxContentInput !== null) {
                this.elemOverlaySearch.searchBoxContentInput.value = this.params.query;
                // Use timeout 0 to empty the callstack ensuring the element has our focus handler by the time it's invoked.
                window.setTimeout(function () {
                    _this.elemOverlaySearch.searchBoxContentInput.focus();
                }, 0);
            }
        }
    };
    Cludo.prototype.setOverlayElements = function () {
        var overlayWrapper = this.getOverlayParentElement();
        if (this.elemOverlaySearch.overlay === null) {
            this.elemOverlaySearch.overlay = this.helpers.addElement(overlayWrapper, 'cludo-search-modal', 'cludo-search-results');
        }
        if (this.elemOverlaySearch.overlayInner === null) {
            this.elemOverlaySearch.overlayInner = this.helpers.addElement(this.elemOverlaySearch.overlay, '', 'cludo-search-modal-inner');
            this.elemOverlaySearch.overlayInner.setAttribute("aria-modal", "true");
            this.elemOverlaySearch.overlayInner.setAttribute("aria-label", this.translateProvider.translate('template_all_results'));
            this.elemOverlaySearch.overlayInner.setAttribute("role", "dialog");
        }
        /* Modal header elements */
        if (this.elemOverlaySearch.overlayHeader === null) {
            this.elemOverlaySearch.overlayHeader = this.helpers.addElement(this.elemOverlaySearch.overlayInner, 'cludo-search-modal-header');
        }
        if (this.elemOverlaySearch.closeButton === null) {
            this.elemOverlaySearch.closeButton = this.helpers.addElement(this.elemOverlaySearch.overlayHeader, '', 'cludo-close');
            this.elemOverlaySearch.closeButton.innerHTML = this.translateProvider.translate('overlay_close_div') + " ";
            this.elemOverlaySearch.closeButtonButton = this.helpers.addButtonElement(this.elemOverlaySearch.closeButton, 'cludo-close-button', 'cludo-close-button', this.translateProvider.translate('overlay_close_button'), null, this.translateProvider.translate('overlay_close_button_title'));
        }
        if (this.elemOverlaySearch.searchBoxContent === null) {
            this.elemOverlaySearch.searchBoxContent = this.helpers.addElement(this.elemOverlaySearch.overlayHeader, '', this.overlaySearchFormWrapperId);
            this.elemOverlaySearch.searchBoxLabel = this.helpers.addLabelElement(this.elemOverlaySearch.searchBoxContent, 'cludo-search-form-content-input', this.translateProvider.translate('search_input_label'));
            this.elemOverlaySearch.searchBoxContentInput = this.helpers.addInputElement(this.elemOverlaySearch.searchBoxContent, 'searchrequestcontent', 'search-input', this.params.query !== '' ? this.params.query : this.initSearchBoxText, 'cludo-search-form-content-input', this.autocompleteParamDefaultValue);
            this.elemOverlaySearch.searchBoxContentButton = this.helpers.addButtonElement(this.elemOverlaySearch.searchBoxContent, 'search-button', 'search-button', this.translateProvider.translate('search_button_text'));
            this.registerSearchFormElement(this.overlaySearchFormWrapperId, false);
        }
        /* Modal body elements */
        if (this.elemOverlaySearch.overlayBody === null) {
            this.elemOverlaySearch.overlayBody = this.helpers.addElement(this.elemOverlaySearch.overlayInner, 'cludo-search-modal-body');
            this.elemOverlaySearch.overlayBody.tabIndex = -1;
        }
        if (this.elemSearchResults.resultCount === null && !this.hideResultsCount && !this.clientTemplates) {
            this.helpers.addElement(this.elemOverlaySearch.overlayBody, 'search-result-count');
        }
        if (this.elemSearchResults.didYouMean === null && !this.hideSearchDidYouMean) {
            this.helpers.addElement(this.elemOverlaySearch.overlayBody, 'search-did-you-mean', '', "complementary");
        }
        if (this.elemSearchResults.filters === null && !this.hideSearchFilters) {
            this.helpers.addElement(this.elemOverlaySearch.overlayBody, 'search-filters');
            this.helpers.addElement(this.elemOverlaySearch.overlayHeader, 'search-filters');
        }
        if (this.elemSearchResults.relatedSearches === null) {
            this.helpers.addElement(this.elemOverlaySearch.overlayHeader, 'search-related');
        }
        if (this.elemSearchResults.results === null) {
            this.helpers.addElement(this.elemOverlaySearch.overlayBody, 'search-results');
        }
        this.endlessScrollSetElements(this.elemOverlaySearch.overlayBody);
        if (this.elemOverlaySearch.poweredByMobile === null) {
            this.elemOverlaySearch.poweredByMobile = this.helpers.addElement(this.elemOverlaySearch.overlayBody, 'cludo-poweredby-mobile');
            this.elemOverlaySearch.poweredByMobile.innerHTML = '<a href="https://cludo.com/?ref=' + this.referalHostName + '&utm_source=' + this.referalHostName + '&utm_medium=logo&utm_campaign=searchlogo' + '" title="' + this.translateProvider.translate('poweredBy_title') + '" target="_blank" rel="noopener" id="cludo-poweredby-link-mobile">Powered by Cludo</a>';
        }
        /* Modal footer elements*/
        if (this.elemOverlaySearch.overlayFooter === null) {
            this.elemOverlaySearch.overlayFooter = this.helpers.addElement(this.elemOverlaySearch.overlayInner, 'cludo-search-modal-footer');
        }
        if (this.elemOverlaySearch.poweredBy === null) {
            this.elemOverlaySearch.poweredBy = this.helpers.addElement(this.elemOverlaySearch.overlayFooter, 'cludo-poweredby');
            this.elemOverlaySearch.poweredBy.innerHTML = '<a href="https://cludo.com/?ref=' + this.referalHostName + '&utm_source=' + this.referalHostName + '&utm_medium=logo&utm_campaign=searchlogo' + '" title="' + this.translateProvider.translate('poweredBy_title') + '" target="_blank" rel="noopener" id="cludo-poweredby-link">Powered by Cludo</a>';
            this.elemOverlaySearch.poweredBy.getElementsByTagName("a")[0].addEventListener("keydown", this.poweredByKeyupEvent, true);
        }
    };
    Cludo.prototype.getOverlayParentElement = function () {
        return document.body;
    };
    Cludo.prototype.overlayAddEventsToSearchElements = function () {
        this.elemOverlaySearch.closeButton.addEventListener('click', this.closeButtonClickEvent, true);
        this.elemOverlaySearch.closeButton.addEventListener('keydown', this.closeButtonKeyupEvent, true);
        window.document.addEventListener('keydown', this.closeButtonWindowKeyupEvent, true);
        this.endlessScrollElements.scrolledElement = this.elemOverlaySearch.overlayBody;
        this.endlessScrollElements.documentElement = this.elemOverlaySearch.overlayBody;
        this.endlessScrollAddScrollEvent();
    };
    Cludo.prototype.overlaySetColorTheme = function () {
        var css = '';
        if (this.themeColor !== '') {
            var mainColorDarken = this.helpers.shadeColor(this.themeColor, -20);
            css += "\
                .cludo-search-modal-body a, .cludo-search-modal-header a{\
                    color: " + this.themeColor + ";\
                }\
                #" + this.overlaySearchFormWrapperId + " input[type=\"search\"] {\
                    border-top: 1px solid " + this.themeColor + ";\
                    border-bottom: 1px solid " + this.themeColor + ";\
                }\
                #cludo-search-form .search_autocomplete li:hover, .cludo-search-form .search_autocomplete li:hover,#" + this.overlaySearchFormWrapperId + " .search_autocomplete li:hover, #cludo-search-form .search_autocomplete li.active, .cludo-search-form .search_autocomplete li.active, #" + this.overlaySearchFormWrapperId + " .search_autocomplete li.active, .cludo-search_autocomplete .search_autocomplete li.active, .cludo-search_autocomplete .search_autocomplete li:hover {\
                    background-color: " + this.themeColor + ";\
                }\
                #cludo-search-results .cludo-search-modal-header .search-filters .search-filters-mobile-button.open {\
                    background-color: " + this.themeColor + ";\
                }\
                #cludo-search-results .search-filters ul a.active {\
                    background-color: " + this.themeColor + ";\
                }\
                #cludo-search-results .cludo-search-modal-body .search-did-you-mean b {\
                    color: " + this.themeColor + ";\
                }\
                #cludo-search-results .cludo-search-modal-body #cludo-load-more {\
                    background-color: " + this.themeColor + ";\
                }\
                #cludo-search-results .cludo-search-modal-body #cludo-load-more:hover {\
                    background-color: " + mainColorDarken + ";\
                }";
        }
        var elementFocusColor = this.elementFocusColor !== '' ? this.elementFocusColor : this.themeColor;
        css += "\
            #cludo-search-results a:focus, #cludo-search-results button:focus, #cludo-search-form button:focus, #cludo-search-form input:focus, #" + this.overlaySearchFormWrapperId + " button:focus, #" + this.overlaySearchFormWrapperId + " input:focus {\
                border-color: " + elementFocusColor + " !important;\
            }";
        if (this.themeBannerColor && this.themeBannerColor.backgroundColor !== '') {
            css += "\
                #cludo-search-results .cludo-search-modal-body .cludo-banner {\
                    background-color: " + this.themeBannerColor.backgroundColor + " !important;\
                }";
        }
        if (this.themeBannerColor && this.themeBannerColor.textColor !== '') {
            css += "\
                #cludo-search-results .cludo-search-modal-body .cludo-banner * {\
                    color: " + this.themeBannerColor.textColor + " !important;\
                }";
        }
        if (this.borderRadius !== 0) {
            css += "\
                .cludo-search-modal-header {\
                    border-radius: " + this.borderRadius + "px " + this.borderRadius + "px 0 0;\
                }\
                .cludo-search-modal-body {\
                    border-radius: 0 0 " + this.borderRadius + "px " + this.borderRadius + "px;\
                }\
                #cludo-search-results .search-filters ul {\
                    border-radius: " + this.borderRadius + "px;\
                }\
                #cludo-search-results .search-filters ul li:first-child a{\
                    border-radius: " + this.borderRadius + "px " + this.borderRadius + "px 0 0;\
                }\
                #cludo-search-results .search-filters ul li:last-child a{\
                    border-radius: 0 0 " + this.borderRadius + "px " + this.borderRadius + "px;\
                }\
                .search-results-item__inner__image img {\
                    border-radius: " + Math.floor(this.borderRadius * 0.75) + "px\
                }";
        }
        if (this.borderRadiusInput !== 0) {
            css += "\
                #cludo-search-form .search-input {\
                    border-radius: " + this.borderRadiusInput + "px;\
                }\
                #cludo-search-form .search-button {\
                    border-radius: 0 " + this.borderRadiusInput + "px " + this.borderRadiusInput + "px 0;\
                }";
        }
        this.helpers.addCssStyles(css);
    };
    Cludo.prototype.overlayCloseModalWithSearch = function () {
        this.isSearchResultPage = false;
        LocationService.setHash('');
        this.helpers.removeClass(document.body, "cludo-search-modal-active");
        this.helpers.removeElement("cludo-search-results");
        this.elemSearchResults = {
            results: null,
            pagination: null,
            filters: null,
            didYouMean: null,
            resultCount: null,
            banner: null
        };
        this.elemOverlaySearch = {
            closeButton: null,
            overlay: null,
            overlayInner: null,
            overlayHeader: null,
            overlayBody: null,
            overlayFooter: null,
            searchWrapper: null,
            searchBox: null,
            searchBoxInput: null,
            searchBoxButton: null,
            searchBoxContent: null,
            searchBoxContentInput: null,
            searchBoxContentButton: null,
            poweredBy: null,
            poweredByMobile: null
        };
        this.endlessScrollElements = {
            loadMore: null,
            backToTop: null
        };
        this.params.query = '';
        this.params.page = 1;
        for (var i = 0, len = this.searchInputsLength; i < len; i++) {
            var searchComponents = this.getSearchComponentsObject(this.searchComponentsKeys[i]);
            if (searchComponents.wrapper != null) {
                var input = searchComponents.wrapper.querySelectorAll('input[type=text]')[0] || searchComponents.wrapper.querySelectorAll('input[type=search]')[0];
                if (input) {
                    input.value = this.initSearchBoxText;
                }
            }
        }
        this.removeSearchComponentsObject(this.overlaySearchFormWrapperId);
    };
    // OVERLAY SEARCH RESULTS EVENT HANDLERS
    Cludo.prototype.closeButtonClickEvent = function () {
        this.overlayCloseModalWithSearch();
    };
    Cludo.prototype.closeButtonWindowKeyupEvent = function (e) {
        var keynum = this.helpers.getKey(e);
        if (keynum === this.helpers.ESC) {
            if (document.getElementById("search_autocomplete")) {
                this.autocompleteRestore();
            }
            else {
                this.overlayCloseModalWithSearch();
            }
        }
    };
    Cludo.prototype.closeButtonKeyupEvent = function (e) {
        var _this = this;
        var keynum = this.helpers.getKey(e);
        if (keynum === this.helpers.TAB && e.shiftKey) {
            this.resetFocusTimerPoweredBy = window.setTimeout(function () {
                document.getElementById('cludo-poweredby-link').focus();
                _this.resetFocusTimerPoweredBy = null;
            }, 100);
        }
    };
    Cludo.prototype.poweredByKeyupEvent = function (e) {
        var keynum = this.helpers.getKey(e);
        if (keynum === this.helpers.TAB && !e.shiftKey) {
            document.getElementById('cludo-close-button').focus();
            e.preventDefault();
        }
    };
    // ENDLESS SCROLL
    Cludo.prototype.endlessScrollSetElements = function (wrapper) {
        if (this.endlessScrollElements.loadMore === null) {
            if (document.getElementById('cludo-load-more')) {
                this.endlessScrollElements.loadMore = document.getElementById('cludo-load-more');
                this.endlessScrollElements.loadMoreButton = this.endlessScrollElements.loadMore.getElementsByTagName("button")[0];
            }
            else {
                this.endlessScrollElements.loadMore = this.helpers.addElement(wrapper, 'cludo-hidden', 'cludo-load-more');
                this.endlessScrollElements.loadMoreButton = this.helpers.addButtonElement(this.endlessScrollElements.loadMore, '', null, this.translateProvider.translate('load_more'));
            }
            this.endlessScrollElements.loadMore.addEventListener('click', this.endlessScrollLoadMoreClickEvent, true);
        }
        if (this.endlessScrollElements.backToTop === null) {
            if (document.getElementById('cludo-back-to-top')) {
                this.endlessScrollElements.backToTop = document.getElementById('cludo-back-to-top');
                this.endlessScrollElements.backToTopButton = this.endlessScrollElements.backToTop.getElementsByTagName("button")[0];
            }
            else {
                this.endlessScrollElements.backToTop = this.helpers.addElement(wrapper, 'cludo-opacity0', 'cludo-back-to-top');
                this.endlessScrollElements.backToTopButton = this.helpers.addButtonElement(this.endlessScrollElements.backToTop, '', null, this.translateProvider.translate('backToTop'));
            }
            this.endlessScrollElements.backToTop.addEventListener('click', this.endlessScrollBackToTopClickEvent, true);
            this.endlessScrollElements.backToTop.addEventListener('keyup', this.endlessScrollBackToTopKeyupEvent, true);
        }
    };
    Cludo.prototype.endlessScrollAddScrollEvent = function () {
        var _this = this;
        this.endlessScrollElements.scrolledElement.addEventListener("scroll", function () {
            _this.endlessScrollScrollEvent();
        });
    };
    Cludo.prototype.endlessScrollLoadMoreClickEvent = function () {
        this.searchEventTriggerQueue.push('paginationNext');
        this.page('next', false);
    };
    Cludo.prototype.endlessScrollBackToTopClickEvent = function () {
        if (this.endlessScrollElements.documentElement) {
            //this.scrollToTop(this.endlessScrollElements.documentElement);
            if (this.isOverlaySearch) {
                this.endlessScrollElements.documentElement.scrollTop = 0;
            }
            else {
                document.documentElement.scrollTop = 0;
                document.body.scrollTop = 0;
            }
            this.endlessScrollElements.documentElement.scrollTop = 0;
            this.helpers.removeClass(this.endlessScrollElements.backToTop, 'cludo-opacity1');
            this.helpers.addClass(this.endlessScrollElements.backToTop, 'cludo-opacity0');
        }
    };
    Cludo.prototype.endlessScrollBackToTopKeyupEvent = function (e) {
        var keynum = this.helpers.getKey(e);
        if (keynum === this.helpers.ENTER) {
            this.elemSearchResults.results.getElementsByTagName("ul")[0].children[0].getElementsByTagName("a")[0].focus();
        }
    };
    Cludo.prototype.endlessScrollScrollEvent = function () {
        var scrollTop = (this.endlessScrollElements.scrolledElement instanceof Window) ? this.endlessScrollElements.scrolledElement.scrollY : this.endlessScrollElements.documentElement.scrollTop;
        var scrollHeight = this.endlessScrollElements.documentElement.scrollHeight;
        var offsetHeight = window.innerHeight || document.documentElement.clientHeight;
        var contentHeight = scrollHeight - offsetHeight - this.endlessScroll.bottomOffset;
        if (contentHeight <= scrollTop && contentHeight != 0 && scrollTop != 0 && !this.isLazyLoading) {
            if (this.params.page < this.endlessScroll.stopAfterPage && this.totalDocuments > this.endlessScroll.resultsPerPage && this.params.page < Math.ceil(this.totalDocuments / this.endlessScroll.resultsPerPage)) {
                this.params.page++;
                this.searchEventTriggerQueue.push('paginationNext');
                this.doSearch();
            }
        }
        if (scrollTop <= 100) {
            this.helpers.removeClass(this.endlessScrollElements.backToTop, 'cludo-opacity1');
            this.helpers.addClass(this.endlessScrollElements.backToTop, 'cludo-opacity0');
        }
        if (scrollTop > 100) {
            this.helpers.removeClass(this.endlessScrollElements.backToTop, 'cludo-opacity0');
            this.helpers.addClass(this.endlessScrollElements.backToTop, 'cludo-opacity1');
        }
    };
    // TRACKING
    Cludo.prototype.track = function (totalDocuments) {
        var _this = this;
        if (totalDocuments !== undefined) {
            console.warn('Warning: totalDocuments parameter for track method will be ignored');
        }
        // Build and send query log to analytics
        var queryLog = this._buildQueryLogObject();
        this.pushQueryLog(queryLog, function () {
            _this.clearSearchMetadata();
            _this._handlePendingAcClick();
        });
    };
    /** Send query log to all enabled analytics integrations */
    Cludo.prototype.trackQuery = function (queryLog) {
        var promises = this.analyticsIntegrationCommunicator.processQueryEvents(queryLog);
        return Promise.all(promises);
    };
    /** Send click log to all enabled analytics integrations */
    Cludo.prototype.trackClick = function (clickLog) {
        var promises = this.analyticsIntegrationCommunicator.processClickEvents(clickLog);
        return Promise.all(promises);
    };
    /** Send related searches log to all enabled analytics integrations that can process related searches */
    Cludo.prototype.trackRelatedSearches = function (relatedSearchesLog) {
        var promises = this.analyticsIntegrationCommunicator.processRelatedSearchEvents(relatedSearchesLog);
        return Promise.all(promises);
    };
    /** Send chat click logs to all enabled analytics integrations that can process chat clicks */
    Cludo.prototype.trackChatClick = function (chatClickLog) {
        this.updateIsTrackedSession();
        var promises = this.analyticsIntegrationCommunicator.processChatClickEvents(chatClickLog);
        return Promise.all(promises);
    };
    // EXTENSIONS
    // limit search with predefined facet
    Cludo.prototype.limitSearch = function (triggeringElelm, predefinedFacet) {
        this.triggeringElelm = triggeringElelm;
        for (var key in predefinedFacet) {
            this.predefinedFacetKey = key;
            this.predefinedFacetValue = predefinedFacet[key][0];
        }
        if (typeof this.triggeringElelm !== 'undefined' && this.triggeringElelm !== null && this.triggeringElelm.checked) {
            this.initFacets = predefinedFacet;
        }
        else {
            this.initFacets = null;
        }
        window.addEventListener("hashchange", this.limitSearchOnHashchange, true);
        window.addEventListener("load", this.limitSearchOnload, true);
    };
    Cludo.prototype.limitSearchOnload = function () {
        var urlParams = this.helpers.getURLParam(this.getQueryParameterVariableName(this.predefinedFacetKey));
        if (typeof urlParams !== 'undefined' && urlParams !== '' && urlParams === this.predefinedFacetValue) {
            this.triggeringElelm.checked = true;
        }
    };
    Cludo.prototype.limitSearchOnHashchange = function () {
        var urlParams = this.helpers.getURLParam(this.getQueryParameterVariableName(this.predefinedFacetKey));
        if (typeof urlParams !== 'undefined' && urlParams !== '' && urlParams !== this.predefinedFacetValue) {
            this.triggeringElelm.checked = false;
            this.initFacets = null;
        }
    };
    Cludo.prototype.toggleMobileNavigation = function (e) {
        var el = e.parentElement.getElementsByTagName('ul')[0];
        // Toogle aria-expanded 
        if (e.getAttribute('aria-expanded')) {
            var isExpanded_1 = e.getAttribute('aria-expanded') === "true";
            // Wrapping setAttribute in a timeout to avoid a weird screenreader/Chrome bug
            window.setTimeout(function () {
                e.setAttribute('aria-expanded', (!isExpanded_1).toString());
            }, 0);
        }
        if (el.style.display !== 'none' && el.style.display !== '') {
            el.style.display = 'none';
            this.helpers.removeClass(e, 'open');
            //this.elemOverlaySearch.searchBoxContent.style.zIndex = "1";
        }
        else {
            el.style.display = 'block';
            this.helpers.addClass(e, 'open');
            //this.elemOverlaySearch.searchBoxContent.style.zIndex = "0";
        }
    };
    Cludo.prototype.toggleDropdown = function (elementId) {
        var el = document.getElementById(elementId);
        if (el.style.display !== 'none' && el.style.display !== '') {
            el.style.display = 'none';
            this.helpers.removeClass(el, 'open');
            //this.elemOverlaySearch.searchBoxContent.style.zIndex = "1";
        }
        else {
            el.style.display = 'block';
            this.helpers.addClass(el, 'open');
            //this.elemOverlaySearch.searchBoxContent.style.zIndex = "0";
        }
    };
    /* START WITH TRACKING METHODS */
    Cludo.prototype.pushClickLog = function (statParams, onComplete) {
        return cludo_awaiter(this, void 0, void 0, function () {
            return cludo_generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, this.trackClick(statParams)];
                    case 1:
                        _a.sent();
                        if (onComplete) {
                            onComplete();
                        }
                        return [2 /*return*/];
                }
            });
        });
    };
    Cludo.prototype.pushQueryLog = function (statParams, onComplete) {
        return cludo_awaiter(this, void 0, void 0, function () {
            return cludo_generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, this.trackQuery(statParams)];
                    case 1:
                        _a.sent();
                        if (onComplete) {
                            onComplete();
                        }
                        return [2 /*return*/];
                }
            });
        });
    };
    Cludo.prototype.pushRelatedSearchesLog = function (statParams, onComplete) {
        return cludo_awaiter(this, void 0, void 0, function () {
            return cludo_generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, this.trackRelatedSearches(statParams)];
                    case 1:
                        _a.sent();
                        if (onComplete) {
                            onComplete();
                        }
                        return [2 /*return*/];
                }
            });
        });
    };
    Cludo.prototype.trackRelatedSearchClickEventHandler = function () {
        var relatedSearchLogObj = this._buildRelatedSearchesLogObject();
        this.pushRelatedSearchesLog(relatedSearchLogObj);
    };
    /**
     * Reads the data attributes from the clicked element and prepares the clickStat object
     *  - Calls the web service to push click data to analytics
     *  - Navigates to the clicked result
     * @param elm
     * @param openingNewWindow
     */
    Cludo.prototype.trackClickEventHandler = function (elm, openingNewWindow) {
        var _this = this;
        if (openingNewWindow === void 0) { openingNewWindow = false; }
        openingNewWindow = openingNewWindow || false;
        this.clickStat = {
            index: elm.getAttribute("data-cludo-index"),
            url: elm.getAttribute("data-cludo-url") || elm.href,
            title: elm.getAttribute("data-cludo-title") || elm.title,
            page: elm.getAttribute("data-cludo-page"),
            logSource: elm.getAttribute("data-cludo-result"),
            objectId: elm.getAttribute("data-cludo-object-id")
        };
        var clickLogObj = this._buildClickLogObject(this.clickStat);
        this.pushClickLog(clickLogObj, function () {
            // If this is opening in a new tab / window, rely on default behavior -- otherwise, navigate to the clicked result manually
            if (!openingNewWindow) {
                _this.goToClickedResult(elm);
            }
        });
    };
    Cludo.prototype.trackClickEventHandlerForRichAutocompleteLink = function (elm) {
        this.clickStat = {
            index: elm.getAttribute("data-cludo-index"),
            url: elm.getAttribute("data-cludo-url") || elm.href,
            title: elm.getAttribute("data-cludo-title") || elm.title,
            page: '1'
        };
    };
    /**
     * Navigates to the clicked result manually (done asynchronously to allow for analytics tracking first); incorporates WCH fragment handling if enabled
     * @param elm The result element that was clicked
     * @param _isNewWindowClick DEPRECATED but kept for backwards compatibility
     */
    Cludo.prototype.goToClickedResult = function (elm, _isNewWindowClick) {
        if (_isNewWindowClick === void 0) { _isNewWindowClick = false; }
        var urlToRedirectTo = this.clickStat.url;
        //check if elm has attribute href
        // if true, set urlToRedirectTo to href value
        var elementHrefAttribute = elm.attributes.getNamedItem('href');
        if (elementHrefAttribute) {
            urlToRedirectTo = elementHrefAttribute.value;
            // if the user clicked a link fragment, have that take priority
            if (this.linkFragment) {
                urlToRedirectTo = urlToRedirectTo.split('#:~:text=')[0];
                urlToRedirectTo += '#:~:text=' + this.linkFragment;
            }
        }
        LocationService.setHref(urlToRedirectTo);
    };
    Cludo.prototype.getSessionId = function () {
        // Whenever we log information to analytics, prevent tracking accross session if the user has opted out of tracking.
        this.updateIsTrackedSession();
        // Use or generate local session ID if tracking is disabled
        if (!this.isPersistentTrackingAllowed()) {
            if (!this.localSessionId) {
                this.localSessionId = this.generateUUID();
            }
            return this.localSessionId;
        }
        return this.getSessionIdFromStorage();
    };
    /**
     * Retrieve the session ID from storage or creates one if it doesn't exist.
     * Also creates or updates the session ID start key
     * @returns The session ID from storage
     */
    Cludo.prototype.getSessionIdFromStorage = function () {
        var storageData = this.storageService.getItem(StorageKey.SessionId) || {
            sessionId: null,
            sessionStart: null
        };
        var currentSessionId = storageData.sessionId, currentSessionStart = storageData.sessionStart;
        if (!currentSessionId || this.sessionExpired(currentSessionStart)) {
            // Create new session and update in dictionary
            storageData = {
                sessionId: this.generateUUID(),
                sessionStart: new Date().toString()
            };
        }
        else {
            // Update sliding expiration
            storageData.sessionStart = new Date().toString();
        }
        this.storageService.setItem(StorageKey.SessionId, storageData);
        return storageData.sessionId;
    };
    Cludo.prototype.getRecentSearchesFromStorage = function () {
        var recentSearches = this.storageService.getItem(StorageKey.RecentSearches);
        return recentSearches || [];
    };
    /** Store recent searches in Storage Service */
    Cludo.prototype.storeRecentSearches = function () {
        this.storageService.setItem(StorageKey.RecentSearches, this.recentSearches);
    };
    /** Clear recent searches in Storage Service */
    Cludo.prototype.clearRecentSearches = function () {
        this.recentSearches = [];
        this.storedRecentSearchesClient = [];
        this.storeRecentSearches();
        if (this.clientTemplates) {
            this.clientTemplatesComponentController.processEvent('afterautocomplete');
        }
    };
    /** Store conversations */
    Cludo.prototype.storeConversations = function (conversations) {
        this.conversationService.storeConversations(conversations);
    };
    /** Get conversations from storage */
    Cludo.prototype.getConversations = function () {
        return this.conversationService.getConversationsFromStorage();
    };
    /** Get trending pages */
    Cludo.prototype.getTrendingPages = function (daysBack, limit, timezone) {
        var trendingPagesRequestOptions = {
            daysBack: daysBack,
            limit: limit,
            timezone: timezone
        };
        var requestOptions = {
            isIntranet: this.intranetSearch,
            authorizationKey: HttpService.getAuthorizationKey(this.customerId, this.engineId, 'SearchKey'),
            contentType: 'application/json',
        };
        return this.trendingPagesService.getTrendingPages(this.customerId, this.engineId, trendingPagesRequestOptions, requestOptions);
    };
    /** Get Popular pages */
    Cludo.prototype.getPopularPages = function (daysBack, limit, timezone) {
        var popularPagesRequestOptions = {
            daysBack: daysBack,
            limit: limit,
            timezone: timezone
        };
        var requestOptions = {
            isIntranet: this.intranetSearch,
            authorizationKey: HttpService.getAuthorizationKey(this.customerId, this.engineId, 'SearchKey'),
            contentType: 'application/json',
        };
        return this.trendingPagesService.getPopularPages(this.customerId, this.engineId, popularPagesRequestOptions, requestOptions);
    };
    /** Get related pages */
    Cludo.prototype.getRelatedPages = function (url, overrideParams) {
        return this.relatedPagesService.getRelatedPages(url, overrideParams);
    };
    Cludo.prototype.sessionExpired = function (startTime) {
        if (!startTime)
            return true;
        return (Math.abs(new Date().getTime() - Date.parse(startTime)) > this.sessionExpiration);
    };
    Cludo.prototype.generateUUID = function () {
        var d = new Date().getTime();
        if (window.performance && typeof window.performance.now === "function") {
            d += performance.now(); // use high-precision timer if available
        }
        var uuid = 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = (d + Math.random() * 16) % 16 | 0;
            d = Math.floor(d / 16);
            return (c == 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
        return uuid;
    };
    /**
     * Determines if this session should be tracked
     * @returns False if customer settings have disabled cookies, or if a user opted out of cookie tracking. Returns true otherwise.
     */
    Cludo.prototype.isPersistentTrackingAllowed = function () {
        if (this.websiteSettings.optOutCookieTracking) {
            return false;
        }
        return this._getIsTrackedSession();
    };
    Cludo.prototype.enableTrackingForUser = function () {
        // If user accepts cookie popup, allow for tracking
        this.storageService.enableTrackingForUser();
    };
    Cludo.prototype.disableTrackingForUser = function () {
        this.storageService.disableTrackingForUser();
    };
    Cludo.prototype.queryIsNullOrEmpty = function () {
        if (this.params && this.params.query) {
            return (this.params.query === '' || this.params.query.replace(/\s/g, '').length <= 0);
        }
        else {
            return true;
        }
    };
    /** Add traits array to search params */
    Cludo.prototype.populateTraitsForRequest = function () {
        this.params.traits = this.getTraitsFromStorage();
    };
    Cludo.prototype.getTraitsFromStorage = function () {
        var storedTraitsValue = this.storageService.getItem(StorageKey.Traits);
        if (!storedTraitsValue) {
            return [];
        }
        try {
            if (!Array.isArray(storedTraitsValue)) {
                throw 'Corrupt data detected in persisted traits';
            }
            return storedTraitsValue;
        }
        catch (_a) {
            return [];
        }
    };
    /** Determines whether the user is searching on desktop, mobile, or tablet by parsing the useragent
     *  @returns "desktop", "mobile", or "tablet"
     */
    Cludo.prototype.getDeviceType = function () {
        var ua = this._getUserAgent();
        if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua) && !/(Tablet PC 2.0)/i.test(ua)) {
            return "tablet";
        }
        if (/Mobile|iP(hone|od|ad)|Android|BlackBerry|IEMobile|Kindle|Silk-Accelerated|(hpw|web)OS|Opera M(obi|ini)/.test(ua)) {
            return "mobile";
        }
        return "desktop";
    };
    // Returns true if quicklink was processed
    Cludo.prototype._handleQuickLinks = function () {
        var _this = this;
        if (!window.quickLinkHandled && this.hasQuicklink()) {
            if (this.customCallbackBeforeQuicklink) {
                this.customCallbackBeforeQuicklink(this.quicklink, this.params.query);
            }
            window.quickLinkHandled = true;
            this.pushQueryLog(this._buildQueryLogObjectForQuickLink(), function () {
                _this.redirectToUrl(_this.quicklink.url);
                if (_this.quicklink.url.indexOf(_this.getQueryParameterVariableName("query")) > -1 && _this.isSearchResultPage && !_this.isOverlaySearch) {
                    location.reload();
                }
            });
            return true;
        }
        else {
            window.quickLinkHandled = false;
        }
        return false;
    };
    // inspiration:: https://developers.google.com/analytics/resources/concepts/gaConceptsTrackingOverview?hl=en 
    Cludo.prototype._buildClickLogObject = function (clickStat) {
        this.updateIsTrackedSession();
        var paramsObj = {
            sz: this._getScreenResolution(),
            ua: this._getUserAgent(),
            refurl: this._getReferralUrl(),
            refpt: this._getReferralPageTitle(),
            sw: this._getSearchWord(),
            brl: this._getBrowserLanguage(),
            pn: clickStat.page ? clickStat.page : '1',
            hn: this._getHostName(),
            enid: this._getEngineId(),
            clurl: clickStat.url,
            cli: clickStat.index,
            title: clickStat.title,
            qid: this._getQueryId(),
            sid: this.getSessionId(),
            qsid: this.querySessionId,
            ts: this.isPersistentTrackingAllowed(),
            dt: this._getDeviceType(),
            it: this._getInputType(),
            trts: this._getTraits(),
            sf: this._getSelectedFacets(),
            ps: this._getResultsPerPage(),
            appi: this._getInitiatorType(),
            // to purge cache
            a: this._getTimestamp()
            // Add categories
        };
        if (clickStat.logSource) {
            paramsObj.ls = clickStat.logSource;
        }
        if (clickStat.objectId) {
            paramsObj.cloi = clickStat.objectId;
        }
        return paramsObj;
    };
    Cludo.prototype._buildQueryLogObject = function () {
        this.updateIsTrackedSession();
        var paramsObj = {
            sz: this._getScreenResolution(),
            ua: this._getUserAgent(),
            refurl: this._getReferralUrl(),
            refpt: this._getReferralPageTitle(),
            sw: this._getSearchWord(),
            swr: this._getSearchWordRaw(),
            brl: this._getBrowserLanguage(),
            pn: this._getPageNumber(),
            hn: this._getHostName(),
            rc: this._getResultCount(),
            enid: this._getEngineId(),
            fquery: this._getFixedQuery(),
            ban: this._getBannersCount(),
            rt: this._getResponseTime(),
            ql: this._getQuicklink(),
            qid: this._getQueryId(),
            sid: this.getSessionId(),
            qsid: this.querySessionId,
            ts: this.isPersistentTrackingAllowed(),
            dt: this._getDeviceType(),
            it: this._getInputType(),
            trts: this._getTraits(),
            sf: this._getSelectedFacets(),
            ety: this._getSearchEventType(),
            etr: this._getSearchEventTrigger(),
            ps: this._getResultsPerPage(),
            appi: this._getInitiatorType(),
            // to purge cache
            a: this._getTimestamp(),
            // Add categories
        };
        // Banners ids
        if (this._getBannersId) {
            paramsObj.bnrs = this._getBannersId();
        }
        return paramsObj;
    };
    Cludo.prototype._buildRelatedSearchesLogObject = function () {
        this.updateIsTrackedSession();
        var paramsObj = {
            sz: this._getScreenResolution(),
            ua: this._getUserAgent(),
            refurl: this._getReferralUrl(),
            refpt: this._getReferralPageTitle(),
            sw: this._getSearchWord(),
            brl: this._getBrowserLanguage(),
            hn: this._getHostName(),
            enid: this._getEngineId(),
            qid: this._getQueryId(),
            sid: this.getSessionId(),
            qsid: this.querySessionId,
            ts: this.isPersistentTrackingAllowed(),
            dt: this._getDeviceType(),
            it: this._getInputType(),
            trts: this._getTraits(),
            pn: this._getPageNumber(),
            ps: this._getResultsPerPage(),
            appi: this._getInitiatorType(),
            // to purge cache
            a: this._getTimestamp(),
            sf: this._getSelectedFacets(),
            // Add categories
        };
        return paramsObj;
    };
    Cludo.prototype._buildQueryLogObjectForQuickLink = function () {
        var paramsObj = this._buildQueryLogObject();
        paramsObj.sw = this.quicklink.matchQuery || this.params.query;
        paramsObj.refurl = this._getCurrentUrl();
        paramsObj.refpt = document.title;
        paramsObj.page = this.params.page;
        paramsObj.ql = this.quicklink.id;
        return paramsObj;
    };
    Cludo.prototype._buildClickLogObjectForRichAutocompleteLink = function () {
        var paramsObj = this._buildClickLogObject(this.clickStat);
        paramsObj.ls = this._getLogSource();
        paramsObj.sw = this.params.query;
        paramsObj.refurl = this._getCurrentUrl();
        paramsObj.refpt = document.title;
        return paramsObj;
    };
    Cludo.prototype._getCurrentUrl = function () {
        return LocationService.getProtocol() + "//" + LocationService.getHostname() + LocationService.getPathname();
    };
    Cludo.prototype._buildQueryLogParameters = function (imageUrl) {
        var statisticsData = this._buildQueryLogObject();
        var finalUrl = HttpService.buildUrl(imageUrl, statisticsData);
        return finalUrl;
    };
    Cludo.prototype._buildPushStatQuery = function (pushStatUrl, parameters) {
        return HttpService.buildUrl(pushStatUrl, parameters);
    };
    // param: rc
    Cludo.prototype._getResultCount = function () {
        return this.totalDocuments;
    };
    // param: ps
    Cludo.prototype._getResultsPerPage = function () {
        return this.params.perPage;
    };
    // Param: sz
    Cludo.prototype._getScreenResolution = function () {
        return screen.width + "x" + screen.height;
    };
    // Param: ua
    Cludo.prototype._getUserAgent = function () {
        return navigator.userAgent;
    };
    // Retrieve the page url from which the search was executed from
    // param: refurl
    Cludo.prototype._getReferralUrl = function () {
        return this.helpers.getURLParam(this.getQueryParameterVariableName("refurl"));
    };
    // param: refpt
    Cludo.prototype._getReferralPageTitle = function () {
        return this.helpers.getURLParam(this.getQueryParameterVariableName("refpt"));
    };
    // param: refact
    Cludo.prototype._getReferralAcTitle = function () {
        return this.helpers.getURLParam(this._getReferralAcTitleKey());
    };
    // param: refaci
    Cludo.prototype._getReferralAcIndex = function () {
        var queryParam = this.helpers.getURLParam(this._getReferralAcIndexKey());
        return queryParam ? parseInt(queryParam) : null;
    };
    Cludo.prototype._getReferralAcTitleKey = function () {
        return this.getQueryParameterVariableName("refact");
    };
    Cludo.prototype._getReferralAcIndexKey = function () {
        return this.getQueryParameterVariableName("refaci");
    };
    // The actual search term performed from URL query param
    // param: sw
    Cludo.prototype._getSearchWord = function () {
        // If changeWindowLocation is false, no search query can be extracted from the URL query parameters
        if (this.changeWindowLocation) {
            return this.getQueryFromUrl();
        }
        else {
            return this.getQueryFromState();
        }
    };
    // The actual search term performed from input value
    // param: swr
    Cludo.prototype._getSearchWordRaw = function () {
        var query = "";
        // TODO: investigate if this should always just get the raw query from the params object
        if (!this.searchInputsLength && this.headlessSearch) {
            query = this.params.query;
        }
        else {
            query = this._getSearchWordFromInputs();
        }
        return query;
    };
    Cludo.prototype._getSearchWordFromInputs = function () {
        var query = "";
        for (var i = 0, len = this.searchInputsLength; i < len; i++) {
            var searchComponents = this.getSearchComponentsObject(this.searchComponentsKeys[i]);
            if (searchComponents.searchBoxInput) {
                if (i > 0) {
                    query += "|";
                }
                query += this.helpers.stripHtmlTags(searchComponents.searchBoxInput.value);
            }
        }
        return query;
    };
    // To track users searches
    // param: clcid
    Cludo.prototype._getCookieId = function () {
        // Should be enabled // disabled based upon law
    };
    // param: brl
    Cludo.prototype._getBrowserLanguage = function () {
        return window.navigator.language;
    };
    // param: pn
    Cludo.prototype._getPageNumber = function () {
        return this.helpers.getURLParam(this.getQueryParameterVariableName('page'));
    };
    // param: hn
    Cludo.prototype._getHostName = function () {
        return LocationService.getHostname();
    };
    // param: enid
    Cludo.prototype._getEngineId = function () {
        return this.engineId;
    };
    // param: fquery
    Cludo.prototype._getFixedQuery = function () {
        return this.fixedQuery;
    };
    // param: rt
    Cludo.prototype._getResponseTime = function () {
        return this.responseTime;
    };
    // param: ql
    Cludo.prototype._getQuicklink = function () {
        return this.helpers.getURLParam(this.getQueryParameterVariableName('ql'));
    };
    // param: ls
    Cludo.prototype._getLogSource = function () {
        return "richautocomplete";
    };
    // param: a
    Cludo.prototype._getTimestamp = function () {
        return new Date().getTime();
    };
    // param: ban
    Cludo.prototype._getBannersCount = function () {
        if (typeof this.banners === 'undefined' || this.banners === null) {
            return 0;
        }
        return this.banners.length;
    };
    // param: bnrs
    Cludo.prototype._getBannersId = function () {
        if (typeof this.banners === 'undefined' || this.banners === null) {
            return [];
        }
        else {
            var bannersId = [];
            for (var i = 0; i < this.banners.length; i++) {
                bannersId.push(this.banners[i].Id);
            }
            return bannersId;
        }
    };
    // param: qid
    Cludo.prototype._getQueryId = function () {
        return this.queryId;
    };
    // param: ts
    // we assume that other mechanisms have updated the isTrackedSession already in this call stack
    // FUTURE -- consider renaming -- this actually returns true if either tracking or unknown
    Cludo.prototype._getIsTrackedSession = function () {
        return this.isTrackedSession !== 0;
    };
    // param: dt
    Cludo.prototype._getDeviceType = function () {
        return this.deviceType;
    };
    // param: it
    Cludo.prototype._getInputType = function () {
        return this.inputType;
    };
    // param: sf
    Cludo.prototype._getSelectedFacets = function () {
        var facets = this.params['facets'];
        var filters = this.params['filters'];
        var selectedFacets = {};
        Helpers.mergeOptions(selectedFacets, facets);
        Helpers.mergeOptions(selectedFacets, filters);
        // initFacets should be removed from the selectedFacets as they are not result of end-user interaction.
        var initFacets = this.initFacets;
        // check only on primary level.
        for (var key in initFacets) {
            if (selectedFacets[key] !== undefined) {
                delete selectedFacets[key];
            }
        }
        return selectedFacets;
    };
    // param: trts
    Cludo.prototype._getTraits = function () {
        var traits = this.getTraitsFromStorage();
        if (traits.length) {
            return traits.join(',');
        }
        else {
            return null;
        }
    };
    // param: ety
    Cludo.prototype._getSearchEventType = function () {
        return this.searchEventType;
    };
    // param: etr
    Cludo.prototype._getSearchEventTrigger = function () {
        return this.searchEventTriggerQueue.shift();
    };
    // param: init
    Cludo.prototype._getInitiatorType = function () {
        // Check explicit prebuilt template types
        if (this.isOverlaySearch)
            return 'overlayTemplate';
        if (this.type === 'inline')
            return 'inlineTemplate';
        // Check for legacy custom templates
        if (!this.clientTemplates)
            return 'customTemplateRazor';
        // Check for Experiences using Core search under the hood
        if (this.paramsPrefix) {
            if (this.paramsPrefix === 'cludo-support-assistant-')
                return 'experienceAiChat';
            if (this.paramsPrefix === 'cludo-fof-')
                return 'experienceFof';
        }
        // Check for Cludo-hosted templates
        if (this._hasCludoHostedTemplate())
            return 'customTemplateReact';
        // If we get here, this is an externally-hosted React template
        return this.headlessSearch ? 'externalReactCore' : 'externalReactController';
    };
    // Check if this page is loading a template from our host server
    // FUTURE: Look into setting this programatically during template init
    Cludo.prototype._hasCludoHostedTemplate = function () {
        var HOST_DIR = 'customer.cludo.com/templates';
        var scripts = Array.from(document.querySelectorAll('script'));
        return scripts.some(function (script) { return script.src.includes(HOST_DIR); });
    };
    /** Initialize based on how the page was loaded */
    Cludo.prototype.initSearchMetadata = function () {
        var perfEntries = [];
        if (performance && performance.getEntriesByType) {
            perfEntries = performance.getEntriesByType('navigation');
        }
        var trigger = perfEntries.length && perfEntries[0].type === 'back_forward' ? 'backButtonAfterResultClick' : 'searchBar';
        this.searchEventTriggerQueue = [trigger];
        this.searchEventType = trigger === 'backButtonAfterResultClick' ? 'secondarySearch' : 'initialSearch';
    };
    /** After a search event has finished processing, clear metadata associated with it */
    Cludo.prototype.clearSearchMetadata = function () {
        this.searchEventType = 'secondarySearch';
    };
    Cludo.prototype._handlePendingAcClick = function () {
        if (this.pendingAcTitle) {
            // Build click stat
            var title = this.pendingAcTitle;
            var index = (this.pendingAcIndex > 0) ? this.pendingAcIndex : 1;
            var clickStat = {
                index: index,
                url: '',
                title: this._getSearchWord(),
                page: 1,
                logSource: 'suggestion',
            };
            var clickLogObj = this._buildClickLogObject(clickStat);
            // override some basic items
            clickLogObj["ls"] = "suggestion";
            clickLogObj["sw"] = title;
            delete clickLogObj["clurl"];
            this.pushClickLog.apply(this, [clickLogObj, function () { }]);
            // clear out pending ac values
            this.pendingAcTitle = null;
            this.pendingAcIndex = null;
        }
    };
    Cludo.prototype._insertTrackingImage = function () {
        var url = this._buildQueryLogParameters(this.searchApiUrl.substr(0, this.searchApiUrl.indexOf("/", 8)) + '/__utm.gif');
        var trackingImage = document.createElement('img');
        trackingImage.setAttribute('src', url);
        trackingImage.style.display = 'none';
        document.body.appendChild(trackingImage);
    };
    Cludo.prototype._isStringMatch = function (query, term) {
        query = query ? query.toUpperCase() : '';
        term = term ? term.toUpperCase() : '';
        if (query == term) {
            return true;
        }
        if (term.indexOf('*') >= 0) {
            // okay, let's do a more complex lookup that takes wildcards into account
            if (query.match(this._wildcardToRegex(term))) {
                return true;
            }
        }
        return false;
    };
    /** Converts our wildcard syntax into RegExp */
    Cludo.prototype._wildcardToRegex = function (pattern) {
        return Helpers.wildcardToRegex(pattern);
    };
    return Cludo;
}());
/* harmony default export */ var cludo = ((/* unused pure expression or super */ null && (Cludo)));
window['Cludo'] = Cludo;

/******/ })()
;