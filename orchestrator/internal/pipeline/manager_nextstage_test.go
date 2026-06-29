package pipeline

import (
	"testing"

	"github.com/dabljaar/orchestrator/internal/db"
)

func TestNextStage_FullDubbingEndsAtMerge(t *testing.T) {
	next, ok := nextStage("fullDubbing", db.JobTypeDubbingMerge)
	if ok {
		t.Fatalf("nextStage(fullDubbing, MERGE) = (%q, true), want (_, false)", next)
	}
}

func TestNextStage_FullDubbingIntermediateStages(t *testing.T) {
	cases := []struct {
		current db.JobType
		want    db.JobType
	}{
		{db.JobTypeSTTTranscribe, db.JobTypeNMTTranslate},
		{db.JobTypeNMTTranslate, db.JobTypeTTSSynthesize},
		{db.JobTypeTTSSynthesize, db.JobTypeDubbingMerge},
	}
	for _, tc := range cases {
		next, ok := nextStage("fullDubbing", tc.current)
		if !ok {
			t.Fatalf("nextStage(fullDubbing, %s) = (_, false), want %s", tc.current, tc.want)
		}
		if next != tc.want {
			t.Errorf("nextStage(fullDubbing, %s) = %q, want %q", tc.current, next, tc.want)
		}
	}
}

func TestNextStage_TranslationAndTTSEndsAtTTS(t *testing.T) {
	next, ok := nextStage("translationAndTTS", db.JobTypeTTSSynthesize)
	if ok {
		t.Fatalf("nextStage(translationAndTTS, TTS) = (%q, true), want (_, false)", next)
	}
}

func TestNextStage_CaptionsAndTranslationEndsAtNMT(t *testing.T) {
	next, ok := nextStage("captionsAndTranslation", db.JobTypeNMTTranslate)
	if ok {
		t.Fatalf("nextStage(captionsAndTranslation, NMT) = (%q, true), want (_, false)", next)
	}
}

func TestNextStage_CaptionsAndTranslationIntermediateStages(t *testing.T) {
	next, ok := nextStage("captionsAndTranslation", db.JobTypeSTTTranscribe)
	if !ok || next != db.JobTypeNMTTranslate {
		t.Errorf("nextStage(captionsAndTranslation, STT) = (%q, %v), want (NMT_TRANSLATE, true)", next, ok)
	}
}

func TestNextStage_CaptionsOnlyEndsAtSTT(t *testing.T) {
	next, ok := nextStage("captionsOnly", db.JobTypeSTTTranscribe)
	if ok {
		t.Fatalf("nextStage(captionsOnly, STT) = (%q, true), want (_, false)", next)
	}
}
