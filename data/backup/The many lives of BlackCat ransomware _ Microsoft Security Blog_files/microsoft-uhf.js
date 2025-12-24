/**
 * Scripting to initialize Microsoft UHF.
 *
 * @package Microsoft-UHF
 */

/* global microsoftUhfSettings */

/* Microsoft UHF requires that jQuery be available via the `$` shortcut. */
if ( 'undefined' === typeof $ && jQuery ) {
	$ = jQuery;
}

(function ($) {
	'use strict';

	/**
	 * Attempt to determine the ID of the current menu item based on its URL.
	 *
	 * @return string
	 */
	var getCurrentMenuItemId = function () {
		var pathname = window.location.pathname,
			links    = $( '#headerArea a[href*="' + trimSlashes( pathname ) + '"]' ),
		    linkId   = '';

		if ( isHomepage() ) {
			linkId = 'c-logo';
		} else if ( 0 < links.length ) {
			linkId = links.last().attr( 'id' );
		}

		// Remove the "-mobile" suffix, as Compass will handle this automatically.
		if ( linkId && '-mobile' === linkId.substr( -7 ) ) {
			linkId = linkId.substr( 0, linkId.length - 7 );
		}

		return linkId;
	},

	/**
	 * Determine if we're currently on the homepage.
	 *
	 * @return boolean
	 */
	isHomepage = function () {
		return trimSlashes( microsoftUhfSettings.homePath ) === trimSlashes( window.location.pathname );
	},

	// Callback to initialize UHF.
	loadShell = function () {
		var settings = {
			currentMenuItemId: getCurrentMenuItemId()
		};

		if ( microsoftUhfSettings.loginUrl || microsoftUhfSettings.logoutUrl ) {
			settings.meControlOptions = {
				rpData: {
					msaInfo: {
						signInUrl: microsoftUhfSettings.loginUrl,
						signOutUrl: microsoftUhfSettings.logoutUrl
					}
				}
			};
		}

		window.onShellReadyToLoad = null;
		window.msCommonShell.load( settings );
	},

	/**
	 * Inject or run scripts that require cookie consent
	 */
	needsConsent = function( ){
		if( microsoftUhfSettings.scripts.length > 0 ){
			microsoftUhfSettings.scripts.forEach( function( script ) {
				var s = document.createElement('script');
				s.type = 'text/javascript';
				s.src = script.src;
				var x = document.getElementsByTagName('script')[0];
				x.parentNode.insertBefore(s, x);
			});
		}
		if( microsoftUhfSettings.inline.length > 0 ){
			microsoftUhfSettings.inline.forEach( function( method ) {
				if( typeof window[method] !== 'undefined' ){
					window[method]();
				}
			});
		}
	},

	/**
	 * Trim slashes from the beginning and end of a string.
	 *
	 * @param string str The string to remove leading and trailing slashes from.
	 * @return string The value of str minus leading/trailing slashes.
	 */
	trimSlashes = function ( str ) {
		if ( '/' === str.substr( 0, 1 ) ) {
			str = str.substr( 1 );
		}

		if ( '/' === str.substr( -1, 1 ) ) {
			str = str.substr( 0, str.length - 1 );
		}

		return str;
	};

	if ( window.msCommonShell ) {
		loadShell();
	} else {
		window.onShellReadyToLoad = loadShell;
	}

	if (  'undefined' === typeof mscc || mscc.hasConsent()) {
		needsConsent();
	} else if (mscc) {
		mscc.on('consent', needsConsent);
	}

  function addRSStoUHF() {
    // Add RSS link to UHF

    var rssTemplate = document.getElementById( 'js-uhf-rss-template' ),
      searchForm;

    /**
     * Bail if there's no rss icon
     */
    if ( rssTemplate === null ) {
      return;
    }

    searchForm = document.getElementById( 'searchForm' );

    /**
     * Bail if there's no UHF searchform
     */

    if ( searchForm === null ) {
      return;
    }

    $( searchForm.parentNode ).prepend( rssTemplate.innerHTML );
  }

  addRSStoUHF();

})(jQuery, undefined);
