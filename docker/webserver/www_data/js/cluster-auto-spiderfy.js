export const AUTO_SPIDERFY_MAX_PINS = 10;
export const AUTO_SPIDERFY_EDGE_MARGIN_PX = 80;

export function shouldAutoSpiderfy({
	visibleClusterCount,
	childCount,
	edgeDistancePixels,
	maxPins = AUTO_SPIDERFY_MAX_PINS,
	edgeMarginPixels = AUTO_SPIDERFY_EDGE_MARGIN_PX,
} = {}) {
	return visibleClusterCount === 1
		&& Number.isInteger(childCount)
		&& childCount >= 2
		&& childCount <= maxPins
		&& Number.isFinite(edgeDistancePixels)
		&& edgeDistancePixels >= edgeMarginPixels;
}
