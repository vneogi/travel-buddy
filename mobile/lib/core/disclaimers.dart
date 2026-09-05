/// SPEC-14: Food recommendation disclaimers.
///
/// Every surface that recommends food or displays ingredient data must show
/// the disclaimer at the point of the recommendation, not only in terms of
/// service.
///
/// Surfaces: driver card, chat food recommendations, venue cards with food
/// category.

/// Full disclaimer for surfaces with space (chat, detail screens).
const String kFoodDisclaimer =
    'Dish data may be incomplete or out of date. '
    'Menus change and no kitchen listed here is audited. '
    'Always confirm ingredients and preparation with the venue.';

/// Short variant for inline captions (driver card footer, venue chip).
const String kFoodDisclaimerShort =
    'Menus change; confirm ingredients with the venue.';
