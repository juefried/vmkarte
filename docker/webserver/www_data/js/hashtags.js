const HASHTAG_BODY = String.raw`[\p{L}][\p{L}\p{M}\p{N}_]+`;

export const HASHTAG_REGEX = new RegExp(`(#${HASHTAG_BODY})`, 'gu');
export const HASHTAG_NAME_REGEX = new RegExp(HASHTAG_BODY, 'u');
