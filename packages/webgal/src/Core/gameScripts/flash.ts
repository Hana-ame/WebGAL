import { ISentence } from '@/Core/controller/scene/sceneInterface';
import { IPerform } from '@/Core/Modules/perform/performInterface';
import { getNumberArgByKey } from '@/Core/util/getSentenceArg';
import * as PIXI from 'pixi.js';
import { WebGAL } from '@/Core/WebGAL';
import { SCREEN_CONSTANTS } from '@/Core/util/constants';

/**
 * 画面闪烁（白闪 / 彩色闪）
 * 语法: flash:#ffffff -duration=1000;
 * 由 RMMZ 224（画面闪烁）迁移而来
 */
export const flash = (sentence: ISentence): IPerform => {
  const colorStr = sentence.content.trim() || '#ffffff';
  const duration = getNumberArgByKey(sentence, 'duration') ?? 1000;

  const performName = `flash${Math.random().toString()}`;
  const tickerKey = `${performName}-ticker`;
  let overlay: PIXI.Graphics | null = null;

  return {
    performName,
    duration: duration,
    isHoldOn: false,
    goNextWhenOver: true,
    blockingNext: () => false,
    blockingAuto: () => false,
    startFunction: () => {
      const pixiStage = WebGAL.gameplay.pixiStage;
      if (!pixiStage?.currentApp) {
        return;
      }
      const color = Number(colorStr.replace('#', '0x'));
      overlay = new PIXI.Graphics();
      overlay.beginFill(color, 1);
      overlay.drawRect(0, 0, SCREEN_CONSTANTS.width, SCREEN_CONSTANTS.height);
      overlay.endFill();
      overlay.alpha = 0;
      overlay.zIndex = 99;
      pixiStage.foregroundEffectsContainer.addChild(overlay);

      const fadeInHalf = duration / 2;
      let startTime = 0;
      pixiStage.registerAnimation(
        {
          setStartState: () => {
            startTime = Date.now();
          },
          setEndState: () => {},
          tickerFunc: () => {
            if (!overlay) return;
            const elapsed = Date.now() - startTime;
            if (elapsed < fadeInHalf) {
              overlay.alpha = elapsed / fadeInHalf;
            } else if (elapsed < duration) {
              overlay.alpha = 1 - (elapsed - fadeInHalf) / fadeInHalf;
            } else {
              overlay.alpha = 0;
            }
          },
        },
        tickerKey,
        'default',
      );
    },
    stopFunction: () => {
      const pixiStage = WebGAL.gameplay.pixiStage;
      pixiStage?.removeAnimationWithoutSetEndState(tickerKey);
      if (overlay) {
        overlay.destroy({ children: true });
        overlay = null;
      }
    },
  };
};
