$(document).ready(function () {

//new script menu
	var interactiveCheck = 0;
	var stringLocate = "";
	if($('.articleContent').length > 0){
		stringLocate  = $('.articleContent').html();
	   
		if(stringLocate .indexOf("[interactive content]") !== -1){

		   interactiveCheck = 1;
		}

	}  
	var globalScrollY;
	$('body').attr('data-scroll-y', $(this).scrollTop());
	$(document).scroll(function() {
	  var y = $(this).scrollTop();
	  $('body').attr('data-scroll-y',y);
	  if (y > 110) {
	  
		$('header .breadcrumb').fadeOut();
		if(interactiveCheck == 1){
			$('header .top-bar').fadeOut();
		}

	  } else {
		$('header .breadcrumb').fadeIn();
		if(interactiveCheck == 1){
		   $('header .top-bar').fadeIn();
		}
	  }
	});


	$('button.search-button').on('click', function(){
		if($(this).attr("aria-expanded")=="true"){
			$('button.search-button').parent().removeClass("open");
			$('button.search-button').attr("aria-expanded","false");
			$('button.search-button').parent().find('.utility-search-target').removeClass("active");
			setTimeout(function(){$('.search-dropdown').removeClass("open"); }, 800);
			setTimeout(function(){$('.search-dropdown').removeClass("open"); }, 1500);
		
		}else{
			$(this).parent().addClass("open");
			$(this).attr("aria-expanded","true");
			$(this).parent().find('.utility-search-target').addClass("active");
			setTimeout(function(){$('.search-dropdown').addClass("open"); }, 1000);
		
		
		}
	});

	$('.search-dropdown .close').on('click', function(){
		$('button.search-button').parent().removeClass("open");
		$('button.search-button').attr("aria-expanded","false");
		$('button.search-button').parent().find('.utility-search-target').removeClass("active");
		setTimeout(function(){$('.search-dropdown').removeClass("open"); }, 800);
		setTimeout(function(){$('.search-dropdown').removeClass("open"); }, 1500);
	});

	$('button.menu-toggle').on('click', function(){

		$('button.search-button').parent().removeClass("open");
		$('button.search-button').attr("aria-expanded",false);
		$('button.search-button').parent().find('.utility-search-target').removeClass("active");
		if(!$(this).parent().hasClass('open')){
			$('button.menu-toggle').attr('aria-expanded', false);
			$('.dropdown').removeClass('open');
			$(this).attr('aria-expanded', true);
			$(this).parent().addClass('open');
		}else{
			$('button.menu-toggle').attr('aria-expanded', false);
			$('.dropdown').removeClass('open');	
		}
	});
	
	$('.utilityMenu-mobile button.menu-button').on('click', function(){
		
		if($(this).attr('aria-expanded')=="true"){

			$('.utilityMenu-mobile .clickMobile').attr('aria-expanded',false);
			$('.utilityMenu-mobile .clickMobile').addClass("collapsed");
			$('.utilityMenu-mobile .clickMobile').removeClass("clickMobile");
			$('.utilityMenu-mobile .collapse-utilityAlerts').removeClass("in");
			$('.utilityMenu-mobile .collapse').removeClass("in");
		
		}else{
			$('.utilityMenu-mobile .clickMobile').attr('aria-expanded',false);
			$('.utilityMenu-mobile .clickMobile').addClass("collapsed");
			$('.utilityMenu-mobile .clickMobile').removeClass("clickMobile");
			$('.utilityMenu-mobile .collapse-utilityAlerts').removeClass("in");
			$('.utilityMenu-mobile .collapse').removeClass("in");
			//$('.utilityMenu-mobile button.menu-button').attr('aria-expanded',false);
			
			var mobileTarget = $(this).attr('data-target');
			
			if($(this).hasClass("collapsed") ){

				$(this).attr('aria-expanded',true);
				$(this).addClass('clickMobile');
				$(this).removeClass("collapsed");
				$(mobileTarget).addClass('in');
				$(mobileTarget).attr('aria-expanded',true);
			}else{

				$(this).removeClass('clickMobile');
				$(this).addClass("collapsed");
				$(mobileTarget).removeClass('in');
				$(mobileTarget).attr('aria-expanded',false);
				$('.utilityMenu-mobile button.menu-button').attr('aria-expanded',false);
			}
		}
		
	});
	

	$('.utilityMenu-desktop button.menu-button').on('click', function(){

		$('.utilityMenu-desktop button.search-button').parent().removeClass("open");
		$('.utilityMenu-desktop button.search-button').attr("aria-expanded",false);
		$('.utilityMenu-desktop button.search-button').parent().find('.utility-search-target').removeClass("active");
		
		if(!$(this).parent().hasClass('open')){		
			$('.utilityMenu-desktop button.menu-button').attr('aria-expanded', false);
			$('.dropdown').removeClass('open');
			$('.dropdown').addClass("position-static");
			$('.utilityMenu').removeClass('position-static');
			$('.inner-container').removeClass('position-relative');
			$('.utility-col').removeClass('position-static');
			$('.utilityMenu__wrapper').removeClass('position-static');
			$(this).attr('aria-expanded', true);
			$(this).parent().addClass('open');
			if($(this).parent().hasClass('stretched-dropdown')){
				$(this).addClass("position-static");
				$('.inner-container').addClass('position-relative');
				$('.utilityMenu').addClass('position-static');
				$('.utility-col').addClass('position-static');
				$('.utilityMenu__wrapper').addClass('position-static');
			}
			
			
			
		}else{
			$('.utilityMenu-desktop button.menu-button').attr('aria-expanded', false);
			$('.dropdown').removeClass('open');
			$('.utilityMenu').removeClass('position-static');
			$('.inner-container').removeClass('position-relative');
			$('.utility-col').removeClass('position-static');
			$('.utilityMenu__wrapper').removeClass('position-static');
			
			
		}
		
		$('button.search-button').parent().removeClass("open");
			$('button.search-button').attr("aria-expanded","false");
			$('button.search-button').parent().find('.utility-search-target').removeClass("active");
			setTimeout(function(){$('.search-dropdown').removeClass("open"); }, 200);
			
	});





	$('body').on('click', function (e) {
		if($(e.target).closest('button.menu-button').length == 0 && $(e.target).closest('button.menu-toggle').length == 0) {
			$('button.menu-toggle').attr('aria-expanded', false);
			$('.dropdown').removeClass('open');	
			$('button.menu-button').attr('aria-expanded', false);
			$('.dropdown').removeClass('open');
			$('.utilityMenu').removeClass('position-static');
			$('.inner-container').removeClass('position-relative');
			$('.utility-col').removeClass('position-static');
			$('.utilityMenu__wrapper').removeClass('position-static');
		}
	});
	
	
	$('.toggle-newnavmenu-mobile').on('click', function(){
		if($(this).hasClass('collapsed')){
			$('body').addClass('active-menu-mobile');
			$(this).attr('aria-expanded',true);
			$(this).removeClass("collapsed");
			$('#newnavmenu-mobile').addClass('in');
			globalScrollY = $('body').attr('data-scroll-y');
			
			closeSearchMob();
		}else{
			closeMobMenu();
		
		}
	});
	
	function closeMobMenu(){
		$('body').removeClass('active-menu-mobile');
		$('.toggle-newnavmenu-mobile').attr('aria-expanded',false);
		$('.toggle-newnavmenu-mobile').addClass("collapsed");
		$('#newnavmenu-mobile').removeClass('in');
		window.scrollTo(0, globalScrollY);
	}
	
	$('.search-mobile').on('click', function(){
		if($(this).hasClass("collapsed")){
			$(this).removeClass("collapsed");
			$(this).attr('aria-expanded',true);
			$('.search-mobile-wrapper').addClass('in');
			$('.search-mobile-wrapper').attr('aria-expanded',true);
			$('.gsc-search-close').removeClass("collapsed");
			$('.gsc-search-close').attr('aria-expanded',true);
			closeMobMenu();
		}else{
			closeSearchMob();
		}
	
	});

	$('.gsc-search-close').on('click', function(){
		closeSearchMob();
		
	});
	
	
	function closeSearchMob(){
		$('.search-mobile').addClass("collapsed");
		$('.search-mobile').attr('aria-expanded',false);
		$('.search-mobile-wrapper').removeClass('in');
		$('.search-mobile-wrapper').attr('aria-expanded',false);
		$('.gsc-search-close').addClass("collapsed");
		$('.gsc-search-close').attr('aria-expanded',false);
	}

//end new script menu


$('.tweetpic').each(function( index ) {
      $(this).parent('a').addClass('tweetpicLink');
 });

if($.trim($('title').text())=="Error Page - Trend Micro Inc."){

$('.product-description-wrap.bg-full.bg-full-mobile').prepend(" <section> <div id=\"product-description-container82ceaf27-790e-4566-bd4c-15be167fa887\" class=\"errorBanner product-description-wrap bg-cover bg-full-mobile  gray-separator \">	<span>					</span>	<section>			<div class=\"prod-desc-content prod-desc-full-width inner-container\">			<div class=\"prod-content\"><div class=\"responsiveColumnControl section\"><style>#responsive-column-2a43109b-45e1-4b0a-ada0-6efb4a2d5b8a {	margin-top:80px;	padding-top:0;	padding-bottom:0;	margin-bottom:80px;}</style><div class=\"row row--extra-padding\" id=\"responsive-column-2a43109b-45e1-4b0a-ada0-6efb4a2d5b8a\">	<div class=\"col-sm-12 col-md-4\"><div class=\"richText section\"><h1><span class=\"rte-white-text\">Oops!</span></h1><h4><span class=\"rte-white-text\">The page you're looking for<br> appears to have been moved,<br> deleted or does not exist.</span></h4></div></div>	<div class=\"col-sm-12 col-md-8\"></div></div></div><div class=\"responsiveColumnControl section\"><style>#responsive-column-7b74db41-d79b-4baf-8f0c-bd7405e5a713 {	margin-top:0;	padding-top:0;	padding-bottom:0;	margin-bottom:0;}</style></div></div>		</div>	</section>		</div>");

}

//alert(document.cookie("trendMicroVisitorViewedAlerts"));

//trendMicroVisitorViewedAlerts


$(".sliding-dismiss-button").on("click", function(){
//TrendMicro.DisruptorPanel.prototype.dismissButtonClickHandler=function(d){var b=d.data.self;
//var c=closest(this,"disruptor-panel__alert");
//var a=c.querySelector(".inner-container > span").getAttribute("data-alert-id");

var c= $(this).parent().parent();
var a = $(this).parent().parent().attr('data-alert-id');

//alert(window.alertsCookie);
window.alertsCookie.dismissAlert(a);
c.addClass('hidden');
var alertCount = $('.menu-button__alert-count').text();
alertCount = (alertCount*1)-1;

if(alertCount>0){
	$('.menu-button__alert-count').text(alertCount);
}else{
	$('.menu-button__alert-count').text(alertCount);
	$('.menu-button__alert-count').addClass('hidden');
	$('.no-alerts').removeClass('hidden');
}

//c.style.height=c.clientHeight+"px";
//setTimeout(addClass,0,c,"dismissing");
//setTimeout(b.removeAlert,350,c,b)
});



    $('.list_Content li').on('click', function () {
        var gotolink = $('.titlelist a', this).attr('href');
        window.location.href = gotolink;
    });


    if ($('.lessen_h1').text() == "Definition") {
        var selectedLetter = $('.nolink').text();

        $("#jumpMenuDefinition").val("/vinfo/us/security/definition/" + selectedLetter.toLowerCase() + "");
    }

    iii = 0;
    $(".mainArticleContainer ul").each(function (i) {

        var countli=0;
	
        if ($('li:not(:has(ul))', this).length > 15) {
          $("li",this).each(function (i) {
         
		if($(this).html().length>6){
			countli=1;
		}

	  });
	  if(countli==0){
            $(this).addClass("longlist");
	  }
        }
	
    });


    if ($(window).width() > 750) {
        equalheight('.list_Content li');
        //equalheight('.list_Content li .titlelist');
        equalheight('.first_Entry');
        equalheight('.hotTopics_Column .link_List li');
        equalheight('.thumblinkbox');
        equalheight('.webAttackHolder li');
        equalheight('.TERecentListHolder .ColHolder ');
    }

    setTimeout(function () {
        equalheight('.list_Content li');
        // equalheight('.list_Content li .titlelist');
        equalheight('.first_Entry');
        equalheight('.hotTopics_Column .link_List li');
        equalheight('.thumblinkbox');
        equalheight('.webAttackHolder li');
        equalheight('.TERecentListHolder .ColHolder ');
    }, 3000);
    if ($('#relatedPostsSection ul').html() == "") {
        $('#relatedPostsSection').css('display', 'none');
    }

    $('.accordion .pane-title h2').on('click', function () {

        if ($(this).parent().next('.pane').css('display') == "none") {
            $(this).parent().addClass('current');
            $(this).parent().next('.pane').css('display', 'block');
        } else {
            $(this).parent().removeClass('current');
            $(this).parent().next('.pane').css('display', 'none');
        }
    });

    //if ($("#downloadReportHolder").length) {

    //    var downloadLink = $("#downloadReportHolder").html();
    //    $('.articleSidepanel').prepend("<div class='downloadSide'>" + downloadLink + "</div>");

    //}

    if ($(".ratingImage").length) {
	var titleArticle = $('.articleHeader h1').text();
        var adjust = 0;
        if (titleArticle.indexOf("DDI RULE") >= 0){
		adjust = 1;
	}else{
		adjust = 0;
	}
        $(".ratingImage").each(function (index) {
            var getRating = $('img', this).attr('title');
            //console.log(getRating)
            var colorbar = "";
            var percentage = 0;
            switch (getRating) {
                case "LOW":
                    colorbar = "#77a542";
                    //percentage = "25%";
                    if(adjust==0){
                       percentage = "25%";
		    }else{
		       percentage = "25%";
		    }
                    break;
                case "SAFE":
                    colorbar = "#77a542";
                    percentage = "25%";
                    break;
                case "MEDIUM":
                    colorbar = "#fda304";
                    //percentage = "50%";
		    if(adjust==0){
                       percentage = "50%";
		    }else{
		       percentage = "75%";
		    }
                    break;
                case "HIGH":
                    colorbar = "#f66c07";
                    if(adjust==0){
                       percentage = "75%";
		    }else{
		       percentage = "100%";
		    }
                    break;
                case "CRITICAL":
                    colorbar = "#060c#f7";
                    percentage = "100%";
                    break;
                case "INFORMATIONAL":
                    colorbar = "#90deee";
                    percentage = "15%";
                    break;

            }
	
		$(this).html("<div class='barHolderRatings'> <div class='barRatingpercentage' style='width:" + percentage + ";background-color:" + colorbar + ";'></div> </div>");

            
        });

    }

 if ($(".iconratingholder").length) {
	
        $(".iconratingholder").each(function (index) {
            var getRating = $('img', this).attr('title');
            //console.log(getRating)
            var colorbar = "";
            var percentage = 0;
            switch (getRating) {
                case "LOW":
                    $('img', this).attr('src', '/vinfo/imgFiles/low.jpg');
                    break;
                case "SAFE":
                     $('img', this).attr('src', '/vinfo/imgFiles/low.jpg');
                    break;
				case "MEDIUM":
					 $('img', this).attr('src', '/vinfo/imgFiles/medium.jpg');
					break;
                case "HIGH":
                    $('img', this).attr('src', '/vinfo/imgFiles/high.jpg');
                    break;
                case "CRITICAL":
                    
                    break;
                case "INFORMATIONAL":
                    $('img', this).attr('src', '/vinfo/imgFiles/informational.jpg');
                    break;

            }
            
        });

    }

    $('.accordion .articleHeader').on("click", function () {
       
        if ($('.pane-title p i', this).hasClass("fa-chevron-circle-up")) {
            $('.pane-title', this).removeClass("current");
            $(this).next('.pane').removeClass("showpane");
            $('.pane-title p i', this).removeClass("fa-chevron-circle-up");
            $('.pane-title p i', this).addClass("fa-chevron-circle-down");
        } else {
            $('.pane-title', this).addClass("current");
            $(this).next('.pane').addClass("showpane");
            $('.pane-title p i', this).removeClass("fa-chevron-circle-down");
            $('.pane-title p i', this).addClass("fa-chevron-circle-up");
        }
    });


    var countpanes = 0;
    $('.panes .accordion').each(function () {
        countpanes=countpanes+1;
        if (countpanes == 1) {
              $('.pane-title',this).addClass("current");
	      $('.pane-title p',this).html('<i class="fa fa-chevron-circle-up" aria-hidden="true"></i>');
              $('.pane',this).addClass("showpane");
        }else{
		$('.pane-title p',this).html('<i class="fa fa-chevron-circle-down" aria-hidden="true"></i>');
	}
    });
    $('.panes .accordion').on("click", function () {
	
        if ($('.pane',this).hasClass("showpane")) {
              $('.pane-title',this).removeClass("current");
              $('.pane',this).removeClass("showpane");
	      $('.pane-title p',this).html('<i class="fa fa-chevron-circle-down" aria-hidden="true"></i>');
        } else {
              $('.pane-title',this).addClass("current");
              $('.pane',this).addClass("showpane");
	      $('.pane-title p',this).html('<i class="fa fa-chevron-circle-up" aria-hidden="true"></i>');
        }

	  

    });



});




function MM_jumpMenu(targ, selObj, restore) { //v3.0
    eval(targ + ".location='" + selObj.options[selObj.selectedIndex].value + "'");
    if (restore) selObj.selectedIndex = 0;
}

$('.gsc-input-box input#gsc-i-id1').focus(function (){
   $(this).keypress(function (e) {
        if (e.which == 13) {
            $('.gsc-search-button-v2').trigger("click");
        }
    });

});

$('.main-menu-search').submit(function( e ) {
     e.preventDefault();
     $('.TESearchButtonHome').trigger("click");
});

$('.gsc-search-button-v2').on('click', function(e){

    e.preventDefault();
   var keywordinput = $('.gsc-input-box input#gsc-i-id1').val();
   keywordinput = keywordinput.replace(/[\|&;\$%@"<>\(\)\+:,]/g, "");
   if(keywordinput!=""){
   	window.location = "https://www.trendmicro.com/en_us/common/cse.html#?cludoquery="+keywordinput+"&cludopage=1";
   }else{
	alert("Keyword is required.");
   }


});


$('.searchTE').focus(function () {


    $(this).keypress(function (e) {
        if (e.which == 13) {
	     e.preventDefault();
            $('.TESearchButtonHome').trigger("click");
        }
    });
});


$(".lightbox").each(function () {
    $(this).attr("target","_blank");
});



$('.TESearchButtonHome').on('click', function () {
    var searchword = $('.searchTE').val().toLowerCase();
   
    searchword = searchword.replace(/[\|&;\$%@"<>\(\)\+:,]/g, "");
    searchword = searchword.replace("*", "-1");
    if (searchword == "search threat encyclopedia" || $.trim(searchword) == "" || searchword.length < 2) {
        alert("Keyword Required");
        return false;

    } else {
	
	//for DDI search
	if($('.inner-container #here').text().toLowerCase()=="ddi detection rules" || $('.inner-container #here').text().toLowerCase()=="network content inspection rules" || $('.inner-container #here').text().toLowerCase().indexOf("ddi rule ") >= 0){
		if($.isNumeric( searchword )){
			searchword = 'DDI RULE '+searchword;
		   } 
	}
	
	if(searchword.slice(0, 1)=="."){
	    searchword = searchword.replace(".","dot-");
	}	

        window.location = "/vinfo/us/threat-encyclopedia/search/" + searchword;

    }

});