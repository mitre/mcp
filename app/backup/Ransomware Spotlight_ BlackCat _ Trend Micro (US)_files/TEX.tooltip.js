$(document).ready(function () {
	var targets = $( '[rel~=tooltip]' ),
		target	= false,
		tooltip = false,
		title	= false;
	$('body').on('click','.closetip', function(){
	    $(this).parent().remove();
	});
	$('.footnote').on('click',function(){
	
		target	= $( this );
		//tip     = target.attr( 'data-note' );
		if($('#tooltip').length){
			tip="";
			$('#tooltip').remove();
		}else{
			tip     = target.attr( 'data-note' );
		}
		tooltip	= $( '<div id="tooltip" class="tooltip_'+target.html()+'" data-id="'+target.html()+'"><div class="closetip">X</div></div>' );
		htmlvar = target.html();
		if( !tip || tip == '' ){
			$('.footnote').each(function() {
				if($(this).html()==htmlvar){
				$(this).attr('data-note',$('.tooltip_'+target.html()).html());
				$('.tooltip_'+target.html()).animate( { top: '-=10', opacity: 0 }, 50, function()
				{
					$('.tooltip_'+target.html()).remove();
				});
				}
			  
			});

			return false;
		}else{

			//$('#tooltip').addClass('tooltip_'+target.html());
		}
               
			
		

		//target.removeAttr( 'data-note' );
		tooltip.css( 'opacity', 0 )
			   .append( tip )
			   .appendTo( 'body' );
		
		var init_tooltip = function()
		{
			if( $( window ).width() < tooltip.outerWidth() * 1.5 )
				tooltip.css( 'max-width', $( window ).width() / 2 );
			else
				tooltip.css( 'max-width', 340 );

			var pos_left = target.offset().left + ( target.outerWidth() / 2 ) - ( tooltip.outerWidth() / 2 ),
				pos_top	 = target.offset().top - tooltip.outerHeight() - 20;

			if( pos_left < 0 )
			{
				pos_left = target.offset().left + target.outerWidth() / 2 - 20;
				tooltip.addClass( 'left' );
			}
			else
				tooltip.removeClass( 'left' );

			if( pos_left + tooltip.outerWidth() > $( window ).width() )
			{
				pos_left = target.offset().left - tooltip.outerWidth() + target.outerWidth() / 2 + 20;
				tooltip.addClass( 'right' );
			}
			else
				tooltip.removeClass( 'right' );

			if( pos_top < 0 )
			{
				var pos_top	 = target.offset().top + target.outerHeight();
				tooltip.addClass( 'top' );
			}
			else
				tooltip.removeClass( 'top' );

			tooltip.css( { left: pos_left, top: pos_top } )
				   .animate( { top: '+=10', opacity: 1 }, 50 );

		};


		init_tooltip();

		$( window ).resize( init_tooltip );

		var remove_tooltip = function()
		{	htmlvar2=$(this).attr('data-id');

			$('.footnote').each(function() {
				if($(this).html()==htmlvar2){
				$(this).attr('data-note',$('.tooltip_'+htmlvar2).html());
				$('.tooltip_'+htmlvar2).animate( { top: '-=10', opacity: 0 }, 50, function()
				{
					$('.tooltip_'+htmlvar2).remove();
				});
				}
			  
			});

			//target.attr( 'title', tip );
			
		};
		//target.bind( 'click', remove_tooltip );
		//target.bind( 'mouseleave', remove_tooltip );
		//tooltip.bind( 'click', remove_tooltip );
		tooltip.bind( 'click', remove_tooltip );
	});
});
