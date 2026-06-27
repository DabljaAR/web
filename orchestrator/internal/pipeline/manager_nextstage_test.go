package pipeline

import (
	"testing"

	"github.com/dabljaar/orchestrator/internal/db"
)

func TestNextStage_FullDubbingEndsAtTTS(t *testing.T) {
	// Bridged TTS path performs merge inside tts_combine_results; no separate merge stage.
	next, ok := nextStage("fullDubbing", db.JobTypeTTSSynthesize)
	if ok {
		t.Fatalf("nextStage(fullDubbing, TTS) = (%q, true), want (_, false)", next)
	}
}

func TestNextStage_FullDubbingIntermediateStages(t *testing.T) {
	cases := []struct {
		current db.JobType
		want    db.JobType
	}{
		{db.JobTypeSTTTranscribe, db.JobTypeNMTTranslate},
		{db.JobTypeNMTTranslate, db.JobTypeTTSSynthesize},
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
