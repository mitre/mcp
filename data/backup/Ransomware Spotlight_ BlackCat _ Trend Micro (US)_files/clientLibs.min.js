$(document).ready(function () {
          $(".footerMenu h3").click(function () {
              if($(this).hasClass('active')){
							$(this).removeClass("active").next().slideUp(500);
              }else{
			$(this).closest('.column').siblings().find('h3').removeClass("active")
              .next()
              .slideUp(500);
              $(this).addClass("active").next().slideDown(500);

              }
          });
          let lang = document.getElementsByTagName('html')[0].lang.toLowerCase().replace('-','_');
          let lang1 = utag_data.language_code;
		$('.country-selection li a').each(function(){
			let _href= $(this).attr('href');
			if(_href.indexOf(lang1) >= 0){
				let region = $(this).text();
				$('#countryMenu .stateSelect').text(region);
				$(this).addClass('active');
				return false;
			}
		});
	 });
